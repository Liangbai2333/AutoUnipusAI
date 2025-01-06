import time
from time import sleep
from typing import Optional

from config import config
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC

from log import logger
from question_handlers import find_handler

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

def login(driver, username: Optional[str] = None, password: Optional[str] = None):
    logger.info("开始登录")
    if not username:
        username = config['unipus']['username']
    if not password:
        password = config['unipus']['password']
    driver.get("https://ucloud.unipus.cn/sso/index.html?service=https%3A%2F%2Fucloud.unipus.cn%2Fhome")
    username_field = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "username"))
    )
    password_field = driver.find_element(By.ID, "password")
    logger.info(f"登录账户: {username}")
    username_field.send_keys(username)
    password_field.send_keys(password)

    agreement_checkbox = driver.find_element(By.ID, "agreement")
    agreement_checkbox.click()

    login_button = driver.find_element(By.CSS_SELECTOR, "button.usso-login-btn")
    login_button.click()
    sleep(1)

def access_book_pages(driver, book: Optional[str] = None):
    if not book:
        book = config['unipus']['book']
    logger.info(f"准备书籍{book}阅读界面")
    driver.get("https://ucloud.unipus.cn/app/cmgt/resource-detail/20000057510")
    time.sleep(1)
    click_button(driver, "button.ant-btn.ant-btn-default.courses-info_buttonLayer1__Mtel4 span")
    click_button(driver,"div.know-box span.iKnow")
    click_button(driver,"button.ant-btn.ant-btn-primary span")
    logger.info(f"成功进入书籍{book}阅读界面")

def get_pages(driver) -> list[WebElement]:
    logger.info(f"获取书籍所有目录, 偏移量: {config['unipus']['offset']}")
    return WebDriverWait(driver, 30).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.pc-slider-menu-micro"))
    )[int(config['unipus']['offset']):]

def access_page(driver, page: WebElement):
    page_name = page.find_element(By.CSS_SELECTOR, "span.pc-menu-node-name").text
    logger.info(f"进入{page_name}页面")
    page.click()
    click_button(driver,"button.ant-btn.ant-btn-primary span")

def auto_answer_questions(driver, page_name: str):
    """
    自动答题核心模块
    :param driver: 驱动器
    :param page_name: 页名
    :return: 答题失败的集合 (不包括检测不到处理器的)
    """
    logger.info(f"开始回答页面{page_name}的问题")
    tab_row = driver.find_element(By.CSS_SELECTOR, "div.ant-row.pc-tab-row")
    tabs = tab_row.find_elements(By.CSS_SELECTOR, "div.tab")
    logger.info(f"检测到页面共有{len(tabs)}个栏目, 开始遍历")
    for index, tab in enumerate(tabs):
        logger.info(f"进入第{index + 1}个栏目: {tab.find_element(By.TAG_NAME, "div").text}")
        tab.click()
        click_button(driver, "button.ant-btn.ant-btn-primary span", 1)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.layout-container"))
        )

        tasks = driver.find_elements(By.CSS_SELECTOR, "div.pc-header-tasks-row>div")
        logger.info(f"页面共有{len(tasks)}个任务, 开始遍历")
        for (index_task, task) in enumerate(tasks):
            def access_internal_with_retry(retry: int):
                if retry > 0:
                    logger.info(f"进入第{index_task + 1}个任务: {task.text} (Retry {retry})")
                else:
                    logger.info(f"进入第{index_task + 1}个任务: {task.text}")
                task.click()
                click_button(driver, "button.ant-btn.ant-btn-primary span", 1)
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.layout-container"))
                )
                handler = find_handler(driver)
                if handler:
                    try:
                        if not handler.handle():
                            if retry < 2:
                                access_internal_with_retry(retry + 1)
                            else:
                                logger.info("做题失败")
                        else:
                            logger.info("做题完成，进入下一题")
                    except Exception as e:
                        logger.warning(f"处理问题时遇到错误", exc_info=e)

            access_internal_with_retry(0)
            time.sleep(float(config['unipus']['task_wait']))
        time.sleep(float(config['unipus']['tab_wait']))
    logger.info("本页任务全部完成!")

