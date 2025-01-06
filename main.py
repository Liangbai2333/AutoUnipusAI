import time

from selenium.webdriver.common.by import By

from config import config
from selenium_handler import get_driver, login, access_book_pages, get_pages, access_page, auto_answer_questions

driver = get_driver()

if __name__ == '__main__':
    login(driver)
    access_book_pages(driver)
    pages = get_pages(driver)
    for page in pages:
        access_page(driver, page)
        auto_answer_questions(driver, page.find_element(By.CSS_SELECTOR, "span.pc-menu-node-name").text)
        time.sleep(float(config['unipus']['page_wait']))


