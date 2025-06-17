import time
from time import sleep
from typing import Optional

from selenium.common import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from handler import find_handler
from util.config import config
from util.log import logger
from util.selenium import click_button


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
    driver.get(f"https://ucloud.unipus.cn/app/cmgt/resource-detail/{book}")
    time.sleep(1)
    click_button(driver, "button.ant-btn.ant-btn-default.courses-info_buttonLayer1__Mtel4 span")
    click_button(driver,"div.know-box span.iKnow")
    click_button(driver,"button.ant-btn.ant-btn-primary span")
    logger.info(f"成功进入书籍{book}阅读界面")
    time.sleep(0.2)

def get_pages(driver) -> list[WebElement]:
    return WebDriverWait(driver, 30).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.pc-slider-menu-micro"))
    )

def access_page(driver, page: WebElement):
    page_name = page.find_element(By.CSS_SELECTOR, "span.pc-menu-node-name").text
    logger.info(f"进入{page_name}页面")
    page.click()
    click_button(driver,"button.ant-btn.ant-btn-primary span")
    time.sleep(0.2)


def auto_answer_questions(driver, page_name, offset_tab, offset_task):
    """
    自动答题核心模块
    :param driver: 驱动器
    :param page_name: 页名
    :param offset_tab 偏移标签
    :param offset_task 便宜任务
    :return: 答题失败的集合 (不包括检测不到处理器的)
    """
    failed_questions = set()
    logger.info(f"开始回答页面{page_name}的问题")

    # 定位并获取所有标签页
    tab_row = driver.find_element(By.CSS_SELECTOR, "div.ant-row.pc-tab-row")
    tabs = tab_row.find_elements(By.CSS_SELECTOR, "div.tab")[offset_tab:]
    logger.info(f"检测到页面共有{len(tabs)}个栏目, 开始遍历")

    # 遍历每个标签页
    for tab_index, tab in enumerate(tabs):
        tab_name = tab.find_element(By.TAG_NAME, "div").text
        logger.info(f"进入第{tab_index}个栏目: {tab_name}")
        clickable_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(tab)
        )
        clickable_tab.click()

        # 点击进入标签页的按钮
        click_button(driver, "button.ant-btn.ant-btn-primary span", 1)

        # 等待页面加载
        wait_for_element(driver, "div.layout-container", timeout=30)

        # 获取当前标签页下的所有任务
        tasks = driver.find_elements(By.CSS_SELECTOR, "div.pc-header-tasks-row>div")[offset_task:]
        logger.info(f"页面共有{len(tasks)}个任务, 开始遍历")

        # 遍历每个任务
        for task_index, task in enumerate(tasks):
            task_result = process_task(driver, task, task_index)
            if not task_result:
                failed_questions.add(f"{page_name}-{tab_name}-Task{task_index}")

            # 任务间等待
            time.sleep(float(config['unipus']['task_wait']))

        # 标签页间等待
        time.sleep(float(config['unipus']['tab_wait']))

    logger.info("本页任务全部完成!")
    return failed_questions


def process_task(driver, task, task_index, max_retries=2):
    """处理单个任务，支持重试机制"""
    for retry in range(max_retries + 1):
        if retry > 0:
            logger.info(f"进入第{task_index}个任务: {task.text} (Retry {retry})")
        else:
            logger.info(f"进入第{task_index}个任务: {task.text}")

        # 点击任务
        clickable_task = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(task)
        )
        clickable_task.click()
        click_button(driver, "button.ant-btn.ant-btn-primary span", 1)

        try:
            # 等待页面加载
            wait_for_element(driver, "div.layout-container", timeout=5)

            # 查找处理器
            handler = find_handler()
            if not handler:
                logger.info("找不到适合的处理器")
                return False

            # 处理问题
            if handler.handle():
                logger.info("做题完成，进入下一题")
                return True
            elif retry < max_retries:
                # 如果处理失败且还有重试次数，继续下一次重试
                continue
            else:
                logger.info("做题失败")
                return False

        except TimeoutException:
            logger.info("不支持处理的页面")
            return False
        except Exception as e:
            logger.warning(f"处理问题时遇到错误", exc_info=e)
            if retry == max_retries:
                return False
        finally:
            # 确保处理完成
            click_button(driver, "button.ant-btn.ant-btn-primary span", 0.5)


    return False


def wait_for_element(driver, css_selector, timeout=10):
    """等待元素出现的封装函数"""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
    )

