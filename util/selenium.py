from typing import Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from util.config import config
from util.log import logger


def get_parent_element(driver, child_element) -> WebElement:
    return driver.execute_script("return arguments[0].parentElement;", child_element)

def get_pure_text(element: WebElement) -> str:
    content = element.get_attribute('outerHTML')
    soup = BeautifulSoup(content, 'lxml')
    return soup.get_text(separator="\n")


def click_button(driver, selector, wait_time=30):
    from selenium.common import TimeoutException
    try:
        button = WebDriverWait(driver, wait_time).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )

        button.click()
    except TimeoutException:
        pass

def find_element_safely(driver, value: Optional[str] = None) -> Optional[WebElement]:
    from selenium.common import NoSuchElementException
    try:
        return driver.find_element(By.CSS_SELECTOR, value)
    except NoSuchElementException:
        return None

def get_driver():
    options = webdriver.ChromeOptions()
    if config['selenium']['headless']:
        options.add_argument('--headless')
    from selenium.webdriver.chrome.service import Service
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.implicitly_wait(config['selenium']['implicit_wait'])
    logger.info("启动浏览器")
    return driver