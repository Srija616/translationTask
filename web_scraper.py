# Focus - get all data  
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

import multiprocessing
import numpy as np
import os
import config
import utils
from bs4 import BeautifulSoup
import time
# Add logging
from indicnlp.tokenize import sentence_tokenize
import pandas as pd
import utils
from utils import tokenizeSentencewise

INDIC = ["as", "bn", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "te"]  # list of indic languages part of IndicTrans library

# instead of string, make a list
def split_sentences(paragraph, language):
    if language == "en":
        return tokenizeSentencewise(paragraph, language)
    elif language in INDIC:
        return sentence_tokenize.sentence_split(paragraph, lang=language)
    
def save_data(directory, file, text):
    file_path = os.path.join(directory, file)
    text.to_csv(file_path, index=False)
    return
    

def extract_text_data(driver, url, visited_urls, url_main):
    '''
    Function to scrape data from input url and other internal urls present on the webpage.
    The function does not return any value, instead the scraped text is stored in all_text string.
    
    Arguments:
    driver: Initialized Chrome Webdriver
    url (string): The url of webpage to be scraped
    visited_urls (list): List of urls already scraped for a given language
    all_text (string): Contains all the text scraped for webpages. 
    
    Output:
    text_data: Returns a string of all scraped data, where each scraped element is delimited by '\n' character
    
    '''
    if url in visited_urls:
        return ""
    visited_urls.add(url)
    driver.get(url)
    driver.implicitly_wait(10)
    
    soup = BeautifulSoup(driver.page_source, 'lxml')
    text_data = soup.body.get_text("\n")

    for link in soup.find_all('a'):
        driver.implicitly_wait(5)
        href = link.get('href')
        driver.implicitly_wait(5)
        try:
            if href.startswith("/"): # only follow internal links to get all data
                data = extract_text_data(driver, url_main+href[1:], visited_urls, url_main)
                if (data != ""):
                        text_data = text_data + "\n "+ (data)
        except Exception as e:
            continue
    return text_data


def get_language_driver(language, driver, url):
    '''
    The function changes the language of the website by opening the dropdown menu on the website and selecting the required language
    
    Arguments:
    language: The language for website to be scraped.
    driver: To interact with the browser
    url: The url of website to be scraped
    
    Output
    driver: Returns the driver to the website
    '''    
    # driver.get(url)
    # driver.implicitly_wait(10)
    # dropdown = driver.find_element('xpath',"//div[@class='language-dropdown dropdown-menu']") # find the dropdown menu
    # driver.execute_script("arguments[0].style.display = 'block';", dropdown) # bring the dropdown menu on page
    # driver.implicitly_wait(10)
    # dropdown.click() # click the dropdown menu
    # # Wait for the option to be clickable
    # option = WebDriverWait(driver, 10).until(
    #     EC.element_to_be_clickable((By.XPATH, "//button[text()='{}']".format(language)))  # get the option to be clicked
    # )
    # option.click() # click the option, the website in required language will open up.
    try:
        response = driver.get(url)
        driver.implicitly_wait(10)
        element = driver.find_element('xpath',"//div[@class='language-dropdown dropdown-menu']")
        driver.execute_script("arguments[0].style.display = 'block';", element)  # bring the element of dropdown-menu visible
        driver.implicitly_wait(10)
        button = driver.find_element('xpath',"//button[text()='{}']".format(language))
        driver.implicitly_wait(10)
        ActionChains(driver).move_to_element(button).click(button).perform()
        driver.implicitly_wait(10)
        return driver
    except Exception as e:
        print (e)
        print (response)
        return
        
        
     
def process_language(args):
    lang, language_isocode, url, url_main = args
    options = Options()
    options.add_experimental_option('excludeSwitches', ['enable-logging']) # to remove a USB related warning message
    driver = webdriver.Chrome(options=options)
    
    try:
        get_language_driver(lang, driver, url) 
    except:
        print ("Unable to get a language driver")
        return  []
    
    visited_urls = set()
    all_text = extract_text_data(driver, url, visited_urls, url_main) # all_text is a string
    driver.quit()
    
    split_text = all_text.split("\n") # split_text is a list of strings - used for translation after some manual cleaning
    
    # there are 22 languages on the website but not all are supported by indicTrans and m2m100 for translation.
    # split_sentences is part of indic-nlp library used to split sentences for indic languages
    if language_isocode in config.common_supported_languages:
        split_text_new = split_sentences(all_text, language_isocode) # don't use it normally, causes issue in alignment
    else:
        split_text_new = split_text

    detected_language = utils.detectLanguage(all_text.replace("\n", ""))
    print (f"language detection of {language_isocode}, detected as {detected_language}, len(split_text) = {len(split_text)}")
    
    if (language_isocode in config.ft_lang_supported): # supported by fastText because we use the detect function
        text_list = utils.removeOtherLanguages(split_text_new, language_isocode)
        text_list = utils.cleanData(text_list)
        text_list = pd.DataFrame({'data': text_list, 'language': language_isocode})
        text_list.drop_duplicates(keep = 'first', inplace= True, ignore_index= True)
        save_data("superCleanSupported", language_isocode + ".csv", text_list)
        
    else:
        split_text_new = utils.cleanData(split_text_new) # cannot remove other languages because the text language itself is not supported
        text_list = pd.DataFrame({'data': split_text_new, 'language': language_isocode})
        text_list.drop_duplicates(keep = 'first', inplace= True, ignore_index= True)
        save_data("superCleanUnsupported", language_isocode + ".csv", text_list)

    return split_text

def get_all_data(url):
    '''
    Given the url, this function extracts all the data and performs the following preprocessing tasks:
    1. Detect language of the extracted data, remove text from other languages from the data.
    2. Store data such that each sentence is one row of the data
    3. Store the data in txt files.
    
    Arguments:
    url : The url of website to be scraped
    
    Output:
    No output. The extracted data is stored in 'raw_data' folder
    '''

    if (len(config.languages) != 0):
        lang_dict = dict(zip(config.languages, config.language_codes)) # key: language on website, language_codes = iso_code for the language
        languages = [lang_dict[lang] for lang in config.languages] # list of all language codes to be used

        with multiprocessing.Pool(processes=1) as pool:
            data = pool.map(process_language, [(lang, lang_dict[lang], url, url_main) for lang in config.languages]) #get all data from websites.
            # data -> [[data for lang1], [data from lang2], [data from lang3], ...]
            # save data for each indic language separately in the folder 'rawBinaryData' where each file is a csv file
            # with col1 -> english and col2 -> indic language
            
        # code block to save the extracted data in csv files
        index_en = languages.index('en')
        df_en=pd.DataFrame(data=data[index_en],columns=[languages[index_en]])  # get the english data
        
        for i in  range(len(languages)):
            if (languages[i] != 'en'):
                df_temp = pd.DataFrame(data=data[i],columns=[languages[i]])
                df = pd.concat([df_en, df_temp], axis=1)
                file = "en_" + languages[i] + ".csv"
                directory = "rawBinaryData"
                file_path = os.path.join(directory, file)
                df.to_csv(file_path, index=False)


if __name__ == "__main__":
    # can add user argument here to run with the requried webpage
    url_main = "https://www.poshantracker.in/"
    get_all_data(url_main)
    