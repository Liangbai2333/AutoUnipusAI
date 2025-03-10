import time
from abc import abstractmethod, ABC
from typing import Union

from bs4 import BeautifulSoup, NavigableString, Tag
from langchain_core.prompts import ChatPromptTemplate
from selenium.common import TimeoutException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from config import config

import audio_parser
import download
from ai_interfaces import chat
from log import logger
from models import *

def get_parent_element(driver, child_element) -> WebElement:
    return driver.execute_script("return arguments[0].parentElement;", child_element)

def get_pure_text(element: WebElement) -> str:
    content = element.get_attribute('outerHTML')
    soup = BeautifulSoup(content, 'lxml')
    return soup.get_text(separator="\n")

def find_element_safely(driver: WebDriver, value: Optional[str] = None) -> Optional[WebElement]:
    from selenium.common import NoSuchElementException
    try:
        return driver.find_element(By.CSS_SELECTOR, value)
    except NoSuchElementException:
        return None

def click_button(driver, selector, wait_time=30):
    from selenium.common import TimeoutException
    try:
        button = WebDriverWait(driver, wait_time).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )

        button.click()
    except TimeoutException:
        pass

class BaseHandler:
    def __init__(self, driver):
        self.retry = 0
        self.driver = driver
        self.score = 0.0
        self.retry_messages = ''

    def _parse_audio_text(self):
        audio_field = self.driver.find_element(By.CSS_SELECTOR, "div.audio-material-wrapper>div>audio.unipus-audio-h5")
        download_url = audio_field.get_attribute("src")
        audio_file_path = download.download_cache_file(download_url, "mp3")
        text = audio_parser.from_audio(audio_file_path)
        return text

    def _parse_video_text(self):
        video_field = self.driver.find_element(By.CSS_SELECTOR, "div.video-material-wrapper video")
        download_url = video_field.get_attribute("src")
        video_file_path = download.download_cache_file(download_url, "mp4")
        text = audio_parser.from_video(video_file_path)
        return text

    def _extract_tips(self) -> list[str]:
        tips = find_element_safely(self.driver, "div.word-tips-wrap")
        tip_list = []
        if tips:
            soup = BeautifulSoup(tips.get_attribute("outerHTML"), 'lxml')
            branches = soup.select("div.qc-abs-word-branch")
            tip_list = []
            for branch in branches:
                title = branch.select_one("h2.word-title").get_text()
                items = branch.select("li.word-item-container")
                word_list = []
                for item in items:
                    word_name = item.select_one("div.word-name").get_text()
                    word_explanation = item.select_one("div.word-explanation").get_text()
                    word_list.append(f"{word_name} {word_explanation}")
                tip_list.append(f"{title}: {' '.join(word_list)}")
        return tip_list

    def __click_button_with_answer(self, selector, wait_time=30) -> bool:
        from selenium.common import TimeoutException
        try:
            button = WebDriverWait(self.driver, wait_time).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            if button.text and (button.text == '查看答题小结' or button.text == "继续学习" or button.text == "继续任务"):
                return False
            button.click()
            return True
        except TimeoutException:
            pass

    @abstractmethod
    def _internal_handle(self) -> Union[None, str, list[str]]:
        pass

    def handle(self) -> bool:
        """
        执行操作
        :return: 大模型给出的答案
        """
        answers = self._internal_handle()
        time.sleep(1)
        return self._post_handle(answers)

    def _post_handle(self, answers) -> bool:
        return True

    def _check_score_with_retry(self, answer) -> bool:
        try:
            score_element = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span.grade"))
            )
            self.score = float(score_element.text)
            if self.score < 60.0:
                raise TimeoutException("Error")
            return True
        except TimeoutException:
            if self.retry < 2:
                logger.info("正确率低于60%, 返回重做")
                click_button(self.driver, "button.ant-btn.ant-btn-primary span", 1)
                if not self.__click_button_with_answer("div.question-common-course-page>a.btn"):
                    return True
                click_button(self.driver, "button.ant-btn.ant-btn-primary span", 1)
                self.retry += 1
                self.retry_messages += f"错误答案: {answer}"
                return self.handle()
            else:
                logger.info("正确率低于60%, 重试三次失败")
                click_button(self.driver, "div.question-common-course-page>a.btn")
                click_button(self.driver, "button.ant-btn.ant-btn-primary span", 1)
                return False

class DiscussionHandler(BaseHandler):
    def _internal_handle(self) -> Optional[str]:
        from selenium.common import TimeoutException
        try:
            others = WebDriverWait(self.driver, 2).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.discussion-cloud-recordList-item'))
            )
            if len(others) >= 5:
                others_contents = [other.find_element(By.CSS_SELECTOR, "div.middle>.content").text for other in others]
                discussion_title = self.driver.find_element(By.CSS_SELECTOR, 'div.discussion-title>p').text
                discussion_content = get_pure_text(self.driver.find_element(By.CSS_SELECTOR, 'div.component-htmlview'))
                prompt = ChatPromptTemplate.from_template(
                    """
                    以下是讨论的话题与别人的讨论内容, 主要根据别人的讨论内容生成一个"平均"的讨论内容，即综合一下, 词汇数要比其他人的讨论内容更少，最好在15-30词之间
                    话题标题: 
                    {topic}
                    话题内容:
                    {content}
                    讨论内容(列表格式):
                    {other_discussions}
                    """
                )
                chain = prompt | chat.with_structured_output(DiscussionAnswer)
                response = chain.invoke(
                    {
                        'topic': discussion_title,
                        'content': discussion_content,
                        'other_discussions': others_contents
                    }
                )
                answer = response.answer
                input_field = self.driver.find_element(By.CSS_SELECTOR, 'textarea.ant-input')
                input_field.clear()
                input_field.send_keys(answer)
                logger.info(f"输入评论: {answer}")
                click_button(self.driver, "div.btns-submit>button.ant-btn")
                logger.info("完成本次讨论答题")
                return answer
            else:
                logger.info("跳过不重要话题 (参与人数少于5)")
                return None
        except TimeoutException:
            logger.info("跳过不重要话题 (参与人数少于5)")
            return None

class GeneralChoiceHandler(BaseHandler):
    @abstractmethod
    def _get_plain_text(self) -> str:
        pass

    def _internal_handle(self) -> list[str]:
        tip_list = self._extract_tips()
        questions = self.driver.find_elements(By.CSS_SELECTOR, "div.question-common-abs-choice")
        multiple_questions_list = []
        single_questions_list = []
        for index, question in enumerate(questions):
            question_soup = BeautifulSoup(question.get_attribute("outerHTML"), 'lxml')
            question_title = question_soup.select_one("div.ques-title").get_text()
            question_options = []
            for option in question_soup.select("div.option"):
                caption = option.select_one("div.caption").get_text()
                content = option.select_one("div.content").get_text()
                question_options.append(Choice(caption=caption, content=content).model_dump_json())
            if "multipleChoice" in question.get_attribute("class").split(" "):
                multiple_questions_list.append(
                    {
                        "title": question_title,
                        "options": question_options
                    }
                )
            else:
                single_questions_list.append(
                    {
                        "title": question_title,
                        "options": question_options
                    }
                )
        prompt = ChatPromptTemplate.from_template(
            """
            你将要通过一些内容与提示推断出最符合问题的答案, 答案以问题的顺序按列表返回
            其他提示通常为错误的答案提示，不可完全重复了
            内容:
            {content}
            提示(列表): 
            {tips}
            单选问题(列表):
            {single_questions}
            多选问题(列表):
            {multiple_questions}
            其他提示: {retry_message}
            """
        )
        chain = prompt | chat.with_structured_output(ChoiceAnswer)

        response = chain.invoke(
            {
                'content': self._get_plain_text(),
                'tips': tip_list,
                'single_questions': single_questions_list,
                'multiple_questions': multiple_questions_list,
                'retry_message': self.retry_messages
            }
        )
        valid_choices = None
        single_choices = response.single_choices
        multiple_choices = response.multiple_choices
        if single_choices:
            valid_choices = single_choices
            for index, choice in enumerate(single_choices):
                option_wrap = self.driver.find_elements(By.CSS_SELECTOR, "div.option-wrap")[index]
                caption = choice.caption
                select_divs = [get_parent_element(self.driver, element) for element in
                               option_wrap.find_elements(By.CSS_SELECTOR, "div.caption")
                               if
                               element.text == caption]
                logger.info(f"单选题{index + 1}选择答案: {caption}")
                if len(select_divs) > 0:
                    select_div = select_divs[0]
                    select_div.click()
                else:
                    logger.info("警告: 大模型返回了错误的答案")
                    get_parent_element(self.driver,
                                       option_wrap.find_elements(By.CSS_SELECTOR, "div.caption")[0]).click()
        if multiple_choices:
            valid_choices = multiple_choices
            for index, choice in enumerate(multiple_choices):
                option_wrap = self.driver.find_elements(By.CSS_SELECTOR, "div.option-wrap")[index]
                captions = choice.captions
                select_divs = [get_parent_element(self.driver, element) for element in
                               option_wrap.find_elements(By.CSS_SELECTOR, "div.caption")
                               if
                               element.text in captions]
                for select_div in select_divs:
                    select_div.click()
                logger.info(f"多选题{index + 1}选择答案: {' '.join(captions)}")
                if len(select_divs) == 0:
                    logger.info("警告: 大模型返回了错误的答案")
                    get_parent_element(self.driver,
                                       option_wrap.find_elements(By.CSS_SELECTOR, "div.caption")[0]).click()
        click_button(self.driver, "div.question-common-course-page>a.btn")
        return valid_choices

class GeneralBlankFillingHandler(BaseHandler, ABC):
    def _fill_blanks(self, answers):
        input_fields = self.driver.find_elements(By.CSS_SELECTOR, 'div.comp-scoop-reply input')
        for index, answer in enumerate(answers):
            logger.info(f"填词第{index + 1}处填写: {answer}")
            if index > len(input_fields) - 1:
                break
            input_fields[index].clear()
            input_fields[index].send_keys(answer)

class MediaBlankFillingHandler(GeneralBlankFillingHandler):
    @abstractmethod
    def _get_plain_text(self) -> str:
        pass

    def _internal_handle(self) -> list[str]:
        tip_list = self._extract_tips()
        areas: list[WebElement] = self.driver.find_elements(By.CSS_SELECTOR, 'div[autodiv="already"]')
        if not areas:
            areas: list[WebElement] = self.driver.find_elements(By.CSS_SELECTOR, 'div.comp-scoop-reply p')
        text_with_blanks = []
        for area in areas:
            soup = BeautifulSoup(area.get_attribute("outerHTML"), 'lxml')
            text_area = ""
            for child in soup.p.children:
                if isinstance(child, NavigableString):
                    text_area += child.text
                else:
                    child: Tag
                    _class: list[str] = child.get("class")
                    if not _class:
                        continue
                    index = int(child.get("data-scoop-index", "-1"))
                    if "fe-scoop" in _class and index >= 0:
                        text_area += f"{index + 1})___"
            #
            # question_text = soup.get_text()
            # text_with_blanks.append(question_text)
        prompt = ChatPromptTemplate.from_template(
            """
            根据下列内容与提示推断 文本内n)处(如1), 2), 3))应填写什么正确的单词形式, 并按照顺序返回单词列表
            其他提示通常为错误的答案提示，不可完全重复了
            内容:
            {content}
            提示(列表): 
            {tips}
            文本:
            {paragraph}
            其他提示: {retry_message}
            """
        )
        chain = prompt | chat.with_structured_output(AudioWithBlankFillingAnswer)
        response = chain.invoke(
            {
                'content': self._get_plain_text(),
                'tips': tip_list,
                'paragraph': text_with_blanks,
                'retry_message': self.retry_messages,
            }
        )
        answers = response.blanks
        super()._fill_blanks(answers)
        click_button(self.driver, "div.question-common-course-page>a.btn")
        return answers

class AudioWithBlankFillingHandler(MediaBlankFillingHandler):
    def _get_plain_text(self) -> str:
        return self._parse_audio_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次音频填词答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次音频填词答题失败, 最终分数: {self.score}")

        return True

class AudioWithChoiceHandler(GeneralChoiceHandler):
    def _get_plain_text(self) -> str:
        return self._parse_audio_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次音频选择答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次音频选择答题失败, 最终分数: {self.score}")

        return True

class IdeaWithInputHandler(BaseHandler, ABC):
    def _input_with_log(self, question_list, answers):
        question_fields = self.driver.find_elements(By.CSS_SELECTOR, "textarea.question-inputbox-input")
        for index, field in enumerate(question_fields):
            logger.info(f"问题: {question_list[index]}, 回答: {answers[index]}")
            field.clear()
            field.send_keys(answers[index])

class IdeaWithAudioOrVideoHandler(IdeaWithInputHandler):
    def _post_handle(self, answers) -> bool:
        logger.info("完成本次观点答题")
        return True

    def _internal_handle(self) -> list[str]:
        tip_list = self._extract_tips()
        video = find_element_safely(self.driver, "div.video-material-wrapper")
        if video:
            content = self._parse_video_text()
        else:
            content = self._parse_audio_text()
        questions = self.driver.find_elements(By.CSS_SELECTOR, "div.question-inputbox")
        question_list = []
        for question in questions:
            question_soup = BeautifulSoup(question.get_attribute("outerHTML"), 'lxml')
            question_title = question_soup.select_one("div.question-inputbox-header").get_text()
            question_list.append(question_title)
        prompt = ChatPromptTemplate.from_template(
            """
            你将要通过一些内容和提示推断出最符合问题的答案, 答案以问题的顺序按列表返回
            内容:
            {content}
            提示(列表): 
            {tips}
            问题(列表):
            {questions}
            """
        )
        chain = prompt | chat.with_structured_output(IdeaWithAudioOrVideoAnswer)
        response = chain.invoke(
            {
                'content': content,
                'tips': tip_list,
                'questions': question_list
            }
        )
        answers = response.answers
        super()._input_with_log(question_list, answers)
        click_button(self.driver, "div.question-common-course-page>a.btn")
        return answers

class IdeaWithArticleHandler(IdeaWithInputHandler):
    def _post_handle(self, answers) -> bool:
        logger.info("完成本次观点答题")
        return True

    def _internal_handle(self) -> list[str]:
        text_soup = BeautifulSoup(
            self.driver.find_element(By.CSS_SELECTOR, "div.text-material-wrapper").get_attribute("outerHTML"), 'lxml')
        questions = self.driver.find_elements(By.CSS_SELECTOR, "div.question-inputbox")
        question_list = []
        for question in questions:
            question_soup = BeautifulSoup(question.get_attribute("outerHTML"), 'lxml')
            question_title = question_soup.select_one("div.question-inputbox-header").get_text()
            question_list.append(question_title)
        prompt = ChatPromptTemplate.from_template(
            """
            你将要通过文章推断出最符合问题的答案, 答案以问题的顺序按列表返回
            文章: 
            {passage}
            问题(列表):
            {questions}
            """
        )
        chain = prompt | chat.with_structured_output(IdeaWithAudioOrVideoAnswer)
        response = chain.invoke(
            {
                'passage': text_soup.get_text(separator="\n"),
                'questions': question_list
            }
        )
        answers = response.answers
        super()._input_with_log(question_list, answers)
        click_button(self.driver, "div.question-common-course-page>a.btn")
        return answers

class VideoWithChoiceHandler(GeneralChoiceHandler):
    def _get_plain_text(self) -> str:
        return self._parse_video_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次视频选择答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次视频选择答题失败, 最终分数: {self.score}")

        return True

class VideoWithBlankFillingHandler(MediaBlankFillingHandler):
    def _get_plain_text(self) -> str:
        return self._parse_video_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次视频填词答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次视频填词答题失败, 最终分数: {self.score}")

        return True

class VideoWatchHandler(BaseHandler):
    def _internal_handle(self):
        videos = self.driver.find_elements(By.TAG_NAME, "video")
        logger.info(f"当前页面共有{len(videos)}个视频, 开始遍历")
        for index, video in enumerate(videos):
            logger.info(f"播放第{index + 1}个视频")
            self.driver.execute_script("arguments[0].play();", video)
            time.sleep(float(config["unipus"]["video_sleep"]))

class ArticleWithChoiceHandler(GeneralChoiceHandler):
    def _get_plain_text(self) -> str:
        text_soup = BeautifulSoup(
            self.driver.find_element(By.CSS_SELECTOR, "div.text-material-wrapper").get_attribute("outerHTML"), 'lxml')
        return text_soup.get_text(separator="\n")

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次文本选择答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次文本选择答题失败, 最终分数: {self.score}")

        return True

class WordCorrectionHandler(GeneralBlankFillingHandler):
    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次词汇纠正答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次词汇纠正答题失败, 最终分数: {self.score}")

        return True

    def _internal_handle(self):
        text_wrapper = self.driver.find_element(By.CSS_SELECTOR, "div.question-common-abs-scoop>div>div")
        text_soup = BeautifulSoup(text_wrapper.get_attribute("outerHTML"), 'lxml')
        for span in text_soup.select("span.fe-scoop"):
            span.replace_with('___')
        text = text_soup.get_text(separator="\n")
        prompt = ChatPromptTemplate.from_template(
            """
            根据下列内容，将文本内的下划线(___)替换为后面括号内正确的英文单词，并使用正确的英文单词形式, 并按照顺序返回英文单词列表
            其他提示通常为错误的答案提示，不可完全重复了
            内容:
            {content}
            其他提示: {retry_message}
            """
        )
        chain = prompt | chat.with_structured_output(WordCorrectionAnswer)
        response = chain.invoke(
            {
                'content': text,
                'retry_message': self.retry_messages,
            }
        )
        answers = response.blanks
        super()._fill_blanks(answers)
        click_button(self.driver, "div.question-common-course-page>a.btn")

def find_handler(driver: WebDriver) -> Optional[BaseHandler]:
    set_timeout = False
    try:
        if driver is None:
            return None
        driver.implicitly_wait(0)
        set_timeout = True
        if find_element_safely(driver, "div.layout-container.discussion-view"):
            logger.info("发现讨论题处理器")
            return DiscussionHandler(driver)
        if find_element_safely(driver, "div.audio-material-wrapper") and find_element_safely(driver, "div.comp-scoop-reply")\
            and not find_element_safely(driver, "div.comp-scoop-reply-dropdown-selection-overflow"):
            logger.info("发现音频填空题处理器")
            return AudioWithBlankFillingHandler(driver)
        if find_element_safely(driver, "div.audio-material-wrapper") and find_element_safely(driver,"div.question-common-abs-choice"):
            logger.info("发现音频选择题处理器")
            return AudioWithChoiceHandler(driver)
        if find_element_safely(driver, "div.video-material-wrapper") and find_element_safely(driver, "div.comp-scoop-reply") \
                and not find_element_safely(driver, "div.comp-scoop-reply-dropdown-selection-overflow"):
            logger.info("发现视频填空题处理器")
            return VideoWithBlankFillingHandler(driver)
        if find_element_safely(driver, "div.video-material-wrapper") and find_element_safely(driver,"div.question-common-abs-choice"):
            logger.info("发现视频选择题处理器")
            return VideoWithChoiceHandler(driver)
        if find_element_safely(driver, "div.text-material-wrapper") and find_element_safely(driver, "div.question-common-abs-choice"):
            logger.info("发现文本选择题处理器")
            return ArticleWithChoiceHandler(driver)
        if find_element_safely(driver, "div.audio-material-wrapper") and find_element_safely(driver, "div.question-inputbox"):
            logger.info("发现音频观点题处理器")
            return IdeaWithAudioOrVideoHandler(driver)
        if find_element_safely(driver, "div.video-material-wrapper") and find_element_safely(driver, "div.question-inputbox"):
            logger.info("发现视频观点题处理器")
            return IdeaWithAudioOrVideoHandler(driver)
        if find_element_safely(driver, "div.text-material-wrapper") and find_element_safely(driver, "div.question-inputbox"):
            logger.info("发现文本观点题处理器")
            return IdeaWithArticleHandler(driver)
        if find_element_safely(driver, "div.layout-reply-container.full") and find_element_safely(driver,"div.comp-scoop-reply"):
            logger.info("发现词汇纠正题处理器")
            return WordCorrectionHandler(driver)
        if find_element_safely(driver, "div.question-video-point-read"):
            logger.info("发现视频观看处理器")
            return VideoWatchHandler(driver)
        logger.info("没有发现处理器处理本页")
        return None
    finally:
        if set_timeout:
            driver.implicitly_wait(1)
