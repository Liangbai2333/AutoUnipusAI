import time

from selenium.webdriver.common.by import By

from config import config
from log import logger
from selenium_handler import get_driver, login, access_book_pages, get_pages, access_page, auto_answer_questions

driver = get_driver()

if __name__ == '__main__':
    logger.warning("请确保你有足够的流量以下载大量的音视频文件")
    logger.warning("如有支持CUDA的显卡, 请开启CUDA以加速计算能力")

    login(driver)
    access_book_pages(driver)
    pages = get_pages(driver)
    for page in pages:
        access_page(driver, page)
        auto_answer_questions(driver, page.find_element(By.CSS_SELECTOR, "span.pc-menu-node-name").text)
        time.sleep(float(config['unipus']['page_wait']))


