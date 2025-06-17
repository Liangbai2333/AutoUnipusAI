import time
from abc import abstractmethod, ABC
from typing import Union

from bs4 import BeautifulSoup, NavigableString, Tag
from langchain_core.prompts import ChatPromptTemplate
from selenium.common import TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from handler.models import *
from runner import driver
from util import audio_parser, download
from util.config import config
from util.llm import llm
from util.log import logger
from util.selenium import click_button, get_parent_element, find_element_safely, get_pure_text


def _parse_audio_text():
    audio_field = driver.find_element(By.CSS_SELECTOR, "div.audio-material-wrapper>div>audio.unipus-audio-h5")
    download_url = audio_field.get_attribute("src")
    audio_file_path = download.download_file(download_url)
    text = audio_parser.from_audio(audio_file_path)
    return text


def _parse_video_text():
    video_field = driver.find_element(By.CSS_SELECTOR, "div.video-material-wrapper video")
    download_url = video_field.get_attribute("src")
    video_file_path = download.download_file(download_url)
    text = audio_parser.from_video(video_file_path)
    return text


def _extract_tips() -> list[str]:
    tips = find_element_safely(driver, "div.word-tips-wrap")
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


def _click_button_with_answer(selector, wait_time=30) -> bool:
    from selenium.common import TimeoutException
    try:
        button = WebDriverWait(driver, wait_time).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )
        button_text =  button.text.strip() if button.text else None
        if button_text and (button_text == '查看答题小结' or button_text == "继续学习" or button_text == "继续任务"):
            return False
        button.click()
        return True
    except TimeoutException:
        return False


class BaseHandler:
    def __init__(self):
        self.retry = 0
        self.score = 0.0
        self.retry_messages = ''

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
            score_element = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span.grade"))
            )
            self.score = float(score_element.text)
            if self.score < 60.0:
                raise TimeoutException("Error")
            return True
        except TimeoutException:
            if self.retry < 2:
                logger.info("正确率低于60%, 返回重做")
                click_button(driver, "button.ant-btn.ant-btn-primary span", 1)
                if not _click_button_with_answer("div.question-common-course-page>a.btn"):
                    return True
                click_button(driver, "button.ant-btn.ant-btn-primary span", 1)
                self.retry += 1
                self.retry_messages += f"错误答案: {answer}"
                return self.handle()
            else:
                logger.info("正确率低于60%, 重试三次失败")
                click_button(driver, "div.question-common-course-page>a.btn")
                click_button(driver, "button.ant-btn.ant-btn-primary span", 1)
                return False

class DiscussionHandler(BaseHandler):
    def _internal_handle(self) -> Optional[str]:
        from selenium.common import TimeoutException
        try:
            others = WebDriverWait(driver, 2).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.discussion-cloud-recordList-item'))
            )
            if len(others) >= 5:
                others_contents = [other.find_element(By.CSS_SELECTOR, "div.middle>.content").text for other in others]
                discussion_title = driver.find_element(By.CSS_SELECTOR, 'div.discussion-title>p').text
                discussion_content = get_pure_text(driver.find_element(By.CSS_SELECTOR, 'div.component-htmlview'))
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
                chain = prompt | llm.with_structured_output(DiscussionAnswer)
                response = chain.invoke(
                    {
                        'topic': discussion_title,
                        'content': discussion_content,
                        'other_discussions': others_contents
                    }
                )
                answer = response.answer
                input_field = driver.find_element(By.CSS_SELECTOR, 'textarea.ant-input')
                input_field.clear()
                input_field.send_keys(answer)
                logger.info(f"输入评论: {answer}")
                click_button(driver, "div.btns-submit>button.ant-btn")
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
        tip_list = _extract_tips()
        questions = driver.find_elements(By.CSS_SELECTOR, "div.question-common-abs-choice")
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
        chain = prompt | llm.with_structured_output(ChoiceAnswer)

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
                option_wrap = driver.find_elements(By.CSS_SELECTOR, "div.option-wrap")[index]
                caption = choice.caption
                select_divs = [get_parent_element(driver, element) for element in
                               option_wrap.find_elements(By.CSS_SELECTOR, "div.caption")
                               if
                               element.text == caption]
                logger.info(f"单选题{index + 1}选择答案: {caption}")
                if len(select_divs) > 0:
                    select_div = select_divs[0]
                    select_div.click()
                else:
                    logger.info("警告: 大模型返回了错误的答案")
                    get_parent_element(driver,
                                       option_wrap.find_elements(By.CSS_SELECTOR, "div.caption")[0]).click()
        if multiple_choices:
            valid_choices = multiple_choices
            for index, choice in enumerate(multiple_choices):
                option_wrap = driver.find_elements(By.CSS_SELECTOR, "div.option-wrap")[index]
                captions = choice.captions
                select_divs = [get_parent_element(driver, element) for element in
                               option_wrap.find_elements(By.CSS_SELECTOR, "div.caption")
                               if
                               element.text in captions]
                for select_div in select_divs:
                    select_div.click()
                logger.info(f"多选题{index + 1}选择答案: {' '.join(captions)}")
                if len(select_divs) == 0:
                    logger.info("警告: 大模型返回了错误的答案")
                    get_parent_element(driver,
                                       option_wrap.find_elements(By.CSS_SELECTOR, "div.caption")[0]).click()
        click_button(driver, "div.question-common-course-page>a.btn")
        return valid_choices

class GeneralBlankFillingHandler(BaseHandler, ABC):
    def _fill_blanks(self, answers):
        input_fields = driver.find_elements(By.CSS_SELECTOR, 'div.comp-scoop-reply input')
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
        tip_list = _extract_tips()
        areas: list[WebElement] = driver.find_elements(By.CSS_SELECTOR, 'div[autodiv="already"]')
        if not areas:
            areas: list[WebElement] = driver.find_elements(By.CSS_SELECTOR, 'div.comp-scoop-reply p')
        text_area = ""
        for area in areas:
            soup = BeautifulSoup(area.get_attribute("outerHTML"), 'lxml')
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
        chain = prompt | llm.with_structured_output(AudioWithBlankFillingAnswer)
        response = chain.invoke(
            {
                'content': self._get_plain_text(),
                'tips': tip_list,
                'paragraph': text_area,
                'retry_message': self.retry_messages,
            }
        )
        answers = response.blanks
        super()._fill_blanks(answers)
        click_button(driver, "div.question-common-course-page>a.btn")
        return answers

class AudioWithBlankFillingHandler(MediaBlankFillingHandler):
    def _get_plain_text(self) -> str:
        return _parse_audio_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次音频填词答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次音频填词答题失败, 最终分数: {self.score}")

        return True

class AudioWithChoiceHandler(GeneralChoiceHandler):
    def _get_plain_text(self) -> str:
        return _parse_audio_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次音频选择答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次音频选择答题失败, 最终分数: {self.score}")

        return True

class IdeaWithInputHandler(BaseHandler, ABC):
    def _input_with_log(self, question_list, answers):
        question_fields = driver.find_elements(By.CSS_SELECTOR, "textarea.question-inputbox-input")
        for index, field in enumerate(question_fields):
            logger.info(f"问题: {question_list[index]}, 回答: {answers[index]}")
            field.clear()
            field.send_keys(answers[index])

class IdeaWithAudioOrVideoHandler(IdeaWithInputHandler):
    def _post_handle(self, answers) -> bool:
        logger.info("完成本次观点答题")
        return True

    def _internal_handle(self) -> list[str]:
        tip_list = _extract_tips()
        video = find_element_safely(driver, "div.video-material-wrapper")
        if video:
            content = _parse_video_text()
        else:
            content = _parse_audio_text()
        questions = driver.find_elements(By.CSS_SELECTOR, "div.question-inputbox")
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
        chain = prompt | llm.with_structured_output(IdeaWithAudioOrVideoAnswer)
        response = chain.invoke(
            {
                'content': content,
                'tips': tip_list,
                'questions': question_list
            }
        )
        answers = response.answers
        super()._input_with_log(question_list, answers)
        click_button(driver, "div.question-common-course-page>a.btn")
        return answers

class IdeaWithArticleHandler(IdeaWithInputHandler):
    def _post_handle(self, answers) -> bool:
        logger.info("完成本次观点答题")
        return True

    def _internal_handle(self) -> list[str]:
        text_soup = BeautifulSoup(
            driver.find_element(By.CSS_SELECTOR, "div.text-material-wrapper").get_attribute("outerHTML"), 'lxml')
        questions = driver.find_elements(By.CSS_SELECTOR, "div.question-inputbox")
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
        chain = prompt | llm.with_structured_output(IdeaWithAudioOrVideoAnswer)
        response = chain.invoke(
            {
                'passage': text_soup.get_text(separator="\n"),
                'questions': question_list
            }
        )
        answers = response.answers
        super()._input_with_log(question_list, answers)
        click_button(driver, "div.question-common-course-page>a.btn")
        return answers

class VideoWithChoiceHandler(GeneralChoiceHandler):
    def _get_plain_text(self) -> str:
        return _parse_video_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次视频选择答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次视频选择答题失败, 最终分数: {self.score}")

        return True

class VideoWithBlankFillingHandler(MediaBlankFillingHandler):
    def _get_plain_text(self) -> str:
        return _parse_video_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次视频填词答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次视频填词答题失败, 最终分数: {self.score}")

        return True

class VideoWatchHandler(BaseHandler):
    def _internal_handle(self):
        video_boxes = driver.find_elements(By.CLASS_NAME, "video-box")
        logger.info(f"当前页面共有{len(video_boxes)}个视频, 开始遍历")
        for index, video_box in enumerate(video_boxes):
            video = video_box.find_element(By.TAG_NAME, "video")
            logger.info(f"播放第{index + 1}个视频")
            driver.execute_script("arguments[0].pause(); arguments[0].play();", video)
            duration = driver.execute_script("return arguments[0].duration;", video)
            try:
                video_box.find_elements(By.CLASS_NAME, "controlBtn")[0].click()  # 倍速按钮
                time.sleep(0.5)
                video_box.find_elements(By.CLASS_NAME, "textOption")[5].click()  # 选择2倍速
                logger.info("视频调整为2倍速播放")
            except Exception:
                logger.info("倍速调整失败")
            logger.info(f"视频时长为{duration / 2}秒, 请耐心等待")
            if config["unipus"]["video_full"]:
                time.sleep(duration / 2)
            else:
                time.sleep(float(config["unipus"]["video_sleep"]))
            logger.info("当前视频播放完毕")

class ArticleWithChoiceHandler(GeneralChoiceHandler):
    def _get_plain_text(self) -> str:
        text_soup = BeautifulSoup(
            driver.find_element(By.CSS_SELECTOR, "div.text-material-wrapper").get_attribute("outerHTML"), 'lxml')
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
        text_wrapper = driver.find_element(By.CSS_SELECTOR, "div.question-common-abs-scoop>div>div")
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
        chain = prompt | llm.with_structured_output(WordCorrectionAnswer)
        response = chain.invoke(
            {
                'content': text,
                'retry_message': self.retry_messages,
            }
        )
        answers = response.blanks
        super()._fill_blanks(answers)
        click_button(driver, "div.question-common-course-page>a.btn")

class GeneralDragElementHandler(BaseHandler):
    @abstractmethod
    def _get_plain_text(self) -> str:
        pass

    def _internal_handle(self) -> list[str]:
        tip_list = _extract_tips()
        elements = driver.find_elements(By.CSS_SELECTOR, "div.sortable-list-wrapper>div#sequenceReplyViewItemText")
        choices = [get_pure_text(element) for element in elements]
        prompt = ChatPromptTemplate.from_template(
            """
            你将要通过一些内容与提示把答案进行排序，将选项的ABCD映射为0123等，然后进行答案排序，按排序后的顺序列表返回,
            如果你觉得信息不足，则随机返回答案顺序
            其他提示通常为错误的答案提示，不可完全重复了
            内容:
            {content}
            提示(列表): 
            {tips}
            选项列表:
            {choices}
            其他提示: {retry_message}
            """
        )
        chain = prompt | llm.with_structured_output(DragElementAnswer)

        response = chain.invoke(
            {
                'content': self._get_plain_text(),
                'tips': tip_list,
                'choices': choices,
                'retry_message': self.retry_messages
            }
        )

        orders: list[int] = response.orders

        # 验证和修复orders
        orders = self.validate_and_fix_orders(orders, len(elements))

        logger.info(f"开始进行拖拽排序, 目标顺序: {orders}")
        logger.info(f"当前选项: {[f'{i}:{choices[i][:20]}...' for i in range(len(choices))]}")

        # 使用改进的拖拽算法
        success = self.perform_optimized_drag_sort(orders, choices)

        if not success:
            logger.error("拖拽排序失败")

        click_button(driver, "div.question-common-course-page>a.btn")
        return [str(order) for order in orders]

    def validate_and_fix_orders(self, orders: list[int], expected_length: int) -> list[int]:
        """
        验证和修复orders数组

        Args:
            orders: 原始顺序数组
            expected_length: 期望长度

        Returns:
            修复后的有效顺序数组
        """
        logger.info(f"验证orders: {orders}, 期望长度: {expected_length}")

        # 如果长度不匹配，先调整长度
        if len(orders) != expected_length:
            logger.warning(f"Orders长度不匹配: {len(orders)} vs {expected_length}")
            if len(orders) < expected_length:
                # 补全缺失的索引
                missing = set(range(expected_length)) - set(orders)
                orders.extend(sorted(missing))
            else:
                # 截断多余的部分
                orders = orders[:expected_length]

        # 检查重复值
        seen = set()
        duplicates = set()
        for item in orders:
            if item in seen:
                duplicates.add(item)
            seen.add(item)

        if duplicates:
            logger.warning(f"发现重复值: {duplicates}")
            # 重建orders数组
            valid_orders = []
            used = set()
            available = set(range(expected_length))

            for item in orders:
                if item not in used and 0 <= item < expected_length:
                    valid_orders.append(item)
                    used.add(item)
                    available.remove(item)

            # 补全缺失的索引
            valid_orders.extend(sorted(available))
            orders = valid_orders

        # 最终验证
        if len(orders) != expected_length or set(orders) != set(range(expected_length)):
            logger.error(f"Orders验证失败，使用默认顺序: {list(range(expected_length))}")
            orders = list(range(expected_length))

        logger.info(f"修复后的orders: {orders}")
        return orders

    def perform_optimized_drag_sort(self, target_orders: list[int], choices: list[str]) -> bool:
        """
        执行优化的拖拽排序 - 使用逐个调整法

        Args:
            target_orders: 目标顺序
            choices: 选项文本列表

        Returns:
            bool: 是否成功
        """
        try:
            actions = ActionChains(driver)
            current_order = list(range(len(target_orders)))

            logger.info(f"开始排序，当前顺序: {current_order}, 目标顺序: {target_orders}")

            # 逐个位置调整到正确位置
            for target_pos in range(len(target_orders)):
                target_element_idx = target_orders[target_pos]
                current_pos = current_order.index(target_element_idx)

                if current_pos == target_pos:
                    logger.debug(f"位置{target_pos}的元素{target_element_idx}已在正确位置")
                    continue

                logger.info(
                    f"调整位置{target_pos}: 将元素{target_element_idx}从位置{current_pos}移动到位置{target_pos}")

                # 执行拖拽移动
                if self.execute_drag_move(current_pos, target_pos, target_element_idx, choices):
                    # 更新current_order以反映移动
                    element = current_order.pop(current_pos)
                    current_order.insert(target_pos, element)
                    logger.debug(f"移动后当前顺序: {current_order}")
                    time.sleep(0.6)  # 等待DOM稳定
                else:
                    logger.error(f"移动失败: 元素{target_element_idx} 从{current_pos}到{target_pos}")
                    return False

            # 最终验证
            return self.verify_final_order(target_orders, choices)

        except Exception as e:
            logger.error(f"拖拽排序过程中发生错误: {e}")
            return False

    def execute_drag_move(self, from_pos: int, to_pos: int, element_idx: int, choices: list[str]) -> bool:
        """
        执行单次拖拽移动 - 使用更精确的方法
        """
        try:
            # 重新获取当前元素列表
            current_elements = driver.find_elements(By.CSS_SELECTOR,
                                                    "div.sortable-list-wrapper>div#sequenceReplyViewItemText")

            if from_pos >= len(current_elements) or to_pos >= len(current_elements):
                logger.error(f"位置索引超出范围: from={from_pos}, to={to_pos}, total={len(current_elements)}")
                return False

            source_element = current_elements[from_pos]

            # 等待源元素可点击
            try:
                WebDriverWait(driver, 5).until(EC.element_to_be_clickable(source_element))
            except:
                logger.warning(f"元素{element_idx}等待超时，尝试直接操作")

            # 滚动到元素可见
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", source_element)
            time.sleep(0.3)

            # 尝试多种拖拽策略
            success = False

            # 策略1: 移动到目标位置的精确坐标
            if not success:
                success = self.try_precise_coordinate_drag(source_element, from_pos, to_pos, current_elements,
                                                           element_idx)

            # 策略2: 使用HTML5拖拽API（如果支持）
            if not success:
                success = self.try_html5_drag(source_element, current_elements[to_pos], element_idx)

            # 策略3: 传统的move_to_element方法
            if not success:
                success = self.try_traditional_drag(source_element, current_elements[to_pos], element_idx)

            if success:
                logger.debug(f"成功拖拽元素{element_idx} ('{choices[element_idx][:15]}...')")

            return success

        except Exception as e:
            logger.error(f"拖拽操作失败: {e}")
            # 确保释放鼠标
            try:
                ActionChains(driver).release().perform()
            except:
                pass
            return False

    def try_precise_coordinate_drag(self, source_element, from_pos: int, to_pos: int, elements: list,
                                    element_idx: int) -> bool:
        """
        使用精确坐标进行拖拽
        """
        try:
            logger.debug(f"尝试精确坐标拖拽: 元素{element_idx} 从{from_pos}到{to_pos}")

            # 获取源元素的位置和大小
            source_rect = source_element.rect
            source_center_x = source_rect['x'] + source_rect['width'] // 2
            source_center_y = source_rect['y'] + source_rect['height'] // 2

            # 计算目标位置
            if to_pos < len(elements):
                target_element = elements[to_pos]
                target_rect = target_element.rect
                target_center_x = target_rect['x'] + target_rect['width'] // 2
                target_center_y = target_rect['y'] + target_rect['height'] // 2

                # 如果是向上移动，拖到目标元素的上方
                if from_pos > to_pos:
                    target_center_y = target_rect['y'] + 5
                # 如果是向下移动，拖到目标元素的下方
                else:
                    target_center_y = target_rect['y'] + target_rect['height'] - 5
            else:
                # 拖到最后
                last_element = elements[-1]
                last_rect = last_element.rect
                target_center_x = last_rect['x'] + last_rect['width'] // 2
                target_center_y = last_rect['y'] + last_rect['height'] + 10

            # 执行拖拽
            actions = ActionChains(driver)
            actions.move_to_element_with_offset(source_element, 0, 0)
            actions.click_and_hold()
            actions.pause(0.3)
            actions.move_by_offset(target_center_x - source_center_x, target_center_y - source_center_y)
            actions.pause(0.3)
            actions.release()
            actions.perform()

            time.sleep(0.5)
            return True

        except Exception as e:
            logger.debug(f"精确坐标拖拽失败: {e}")
            try:
                ActionChains(driver).release().perform()
            except:
                pass
            return False

    def try_html5_drag(self, source_element, target_element, element_idx: int) -> bool:
        """
        尝试使用HTML5 drag and drop API
        """
        try:
            logger.debug(f"尝试HTML5拖拽: 元素{element_idx}")

            # JavaScript拖拽代码
            js_drag_script = """
            function simulateDragDrop(sourceElement, targetElement) {
                var dragEvent = new DragEvent('dragstart', {bubbles: true});
                var dropEvent = new DragEvent('drop', {bubbles: true});
                var dragOverEvent = new DragEvent('dragover', {bubbles: true});

                sourceElement.dispatchEvent(dragEvent);
                targetElement.dispatchEvent(dragOverEvent);
                targetElement.dispatchEvent(dropEvent);
            }
            simulateDragDrop(arguments[0], arguments[1]);
            """

            driver.execute_script(js_drag_script, source_element, target_element)
            time.sleep(0.5)
            return True

        except Exception as e:
            logger.debug(f"HTML5拖拽失败: {e}")
            return False

    def try_traditional_drag(self, source_element, target_element, element_idx: int) -> bool:
        """
        传统的拖拽方法
        """
        try:
            logger.debug(f"尝试传统拖拽: 元素{element_idx}")

            actions = ActionChains(driver)
            actions.click_and_hold(source_element)
            actions.pause(0.5)
            actions.move_to_element(target_element)
            actions.pause(0.5)
            actions.release()
            actions.perform()

            time.sleep(0.5)
            return True

        except Exception as e:
            logger.debug(f"传统拖拽失败: {e}")
            try:
                ActionChains(driver).release().perform()
            except:
                pass
            return False

    def verify_final_order(self, expected_orders: list[int], original_choices: list[str]) -> bool:
        """
        验证最终顺序是否正确
        """
        try:
            time.sleep(1)  # 等待所有动画完成

            final_elements = driver.find_elements(By.CSS_SELECTOR,
                                                  "div.sortable-list-wrapper>div#sequenceReplyViewItemText")
            actual_texts = [get_pure_text(elem) for elem in final_elements]
            expected_texts = [original_choices[i] for i in expected_orders]

            logger.info(f"期望的最终顺序: {expected_orders}")
            logger.info(f"期望的文本顺序: {[text[:15] + '...' for text in expected_texts]}")
            logger.info(f"实际的文本顺序: {[text[:15] + '...' for text in actual_texts]}")

            # 计算实际的索引顺序
            actual_orders = []
            for actual_text in actual_texts:
                for i, original_text in enumerate(original_choices):
                    if actual_text.strip() == original_text.strip():
                        actual_orders.append(i)
                        break
                else:
                    logger.warning(f"无法匹配文本: {actual_text[:30]}")
                    return False

            logger.info(f"实际的索引顺序: {actual_orders}")

            if actual_orders == expected_orders:
                logger.info("拖拽排序完全成功！")
                return True
            else:
                logger.warning("拖拽排序结果与期望不符")
                # 显示差异
                for i, (expected, actual) in enumerate(zip(expected_orders, actual_orders)):
                    if expected != actual:
                        logger.warning(f"位置{i}: 期望元素{expected}, 实际元素{actual}")
                return False

        except Exception as e:
            logger.error(f"验证最终顺序失败: {e}")
            return False

class AudioDragElementHandler(GeneralDragElementHandler):
    def _get_plain_text(self) -> str:
        return _parse_audio_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次音频拖拽答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次音频拖拽答题失败, 最终分数: {self.score}")

        return True

class VideoDragElementHandler(GeneralDragElementHandler):
    def _get_plain_text(self) -> str:
        return _parse_video_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次视频拖拽答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次视频拖拽答题失败, 最终分数: {self.score}")

        return True

class GeneralSelectionHandler(BaseHandler):
    @abstractmethod
    def _get_plain_text(self) -> str:
        pass

    def _internal_handle(self) -> list[str]:
        questions = driver.find_elements(By.CSS_SELECTOR, "div.comp-scoop-reply-dropdown-selection-overflow tbody>tr > *:nth-child(2)")

        question_list = []
        for question in questions:
            soup = BeautifulSoup(question.get_attribute("outerHTML"), 'lxml')
            direct_text = ''

            for children in soup.td.children:
                if isinstance(children, NavigableString):
                    direct_text += children.text
            ol = soup.find("ol")
            li_elements = ol.find_all("li") if ol else []
            question_list.append(
                {
                    "question": direct_text,
                    "options": [Choice(caption=str(index), content=li.get_text()) for index, li in enumerate(li_elements)]
                }
            )

        print(question_list)

        prompt = ChatPromptTemplate.from_template(
            """
            你将要通过一些内容与提示推断出最符合问题的答案, 每个问题的答案选择数字选项的其中一个, 答案以问题的顺序按列表返回
            其他提示通常为错误的答案提示，不可完全重复了
            内容:
            {content}
            提示(列表): 
            {tips}
            答案:
            {choices}
            其他提示: {retry_message}
            """
        )
        chain = prompt | llm.with_structured_output(SelectionAnswer)

        response = chain.invoke(
            {
                'content': self._get_plain_text(),
                'tips': _extract_tips(),
                'choices': question_list,
                'retry_message': self.retry_messages
            }
        )

        captions: list[int] = response.captions

        logger.info(f"下拉选择答题目标答案: {captions}")

        if len(captions) != len(questions):
            logger.warning("答案数量不足，请检查答案数量是否正确")
        else:
            for index, question in enumerate(questions):
                selection_element = question.find_element(By.CSS_SELECTOR,
                                                          "span.scoop-select-wrapper>span.input-wrapper")
                selection_button = selection_element.find_element(By.CSS_SELECTOR, "span.ant-dropdown-trigger")
                selection_button.click()
                time.sleep(0.2)
                selections = selection_element.find_elements(By.CSS_SELECTOR, "li")
                if but := selections[captions[index]]:
                    but.click()

        click_button(driver, "div.question-common-course-page>a.btn")
        return [str(caption) for caption in captions]

class AudioSelectionHandler(GeneralSelectionHandler):
    def _get_plain_text(self) -> str:
        return _parse_audio_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次音频下拉选择答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次音频下拉选择答题失败, 最终分数: {self.score}")

        return True

class VideoSelectionHandler(GeneralSelectionHandler):
    def _get_plain_text(self) -> str:
        return _parse_video_text()

    def _post_handle(self, answers) -> bool:
        if self._check_score_with_retry(answers):
            logger.info(f"完成本次视频下拉选择答题, 最终分数: {self.score}")
        else:
            logger.info(f"本次视频下拉选择答题失败, 最终分数: {self.score}")

        return True



def find_handler() -> Optional[BaseHandler]:
    set_timeout = False
    try:
        if driver is None:
            return None
        driver.implicitly_wait(0)
        set_timeout = True
        # if find_element_safely(driver, "div.layout-container.discussion-view"):
        #     logger.info("发现讨论题处理器")
        #     return DiscussionHandler()
        # if find_element_safely(driver, "div.audio-material-wrapper") and find_element_safely(driver, "div.comp-scoop-reply")\
        #     and not find_element_safely(driver, "div.comp-scoop-reply-dropdown-selection-overflow"):
        #     logger.info("发现音频填空题处理器")
        #     return AudioWithBlankFillingHandler()
        # if find_element_safely(driver, "div.audio-material-wrapper") and find_element_safely(driver,"div.question-common-abs-choice"):
        #     logger.info("发现音频选择题处理器")
        #     return AudioWithChoiceHandler()
        # if find_element_safely(driver, "div.video-material-wrapper") and find_element_safely(driver, "div.comp-scoop-reply") \
        #         and not find_element_safely(driver, "div.comp-scoop-reply-dropdown-selection-overflow"):
        #     logger.info("发现视频填空题处理器")
        #     return VideoWithBlankFillingHandler()
        # if find_element_safely(driver, "div.video-material-wrapper") and find_element_safely(driver,"div.question-common-abs-choice"):
        #     logger.info("发现视频选择题处理器")
        #     return VideoWithChoiceHandler()
        # if find_element_safely(driver, "div.text-material-wrapper") and find_element_safely(driver, "div.question-common-abs-choice"):
        #     logger.info("发现文本选择题处理器")
        #     return ArticleWithChoiceHandler()
        # if find_element_safely(driver, "div.audio-material-wrapper") and find_element_safely(driver, "div.question-inputbox"):
        #     logger.info("发现音频观点题处理器")
        #     return IdeaWithAudioOrVideoHandler()
        # if find_element_safely(driver, "div.video-material-wrapper") and find_element_safely(driver, "div.question-inputbox"):
        #     logger.info("发现视频观点题处理器")
        #     return IdeaWithAudioOrVideoHandler()
        # if find_element_safely(driver, "div.text-material-wrapper") and find_element_safely(driver, "div.question-inputbox"):
        #     logger.info("发现文本观点题处理器")
        #     return IdeaWithArticleHandler()
        # if find_element_safely(driver, "div.layout-reply-container.full") and find_element_safely(driver,"div.comp-scoop-reply"):
        #     logger.info("发现词汇纠正题处理器")
        #     return WordCorrectionHandler()
        # if find_element_safely(driver, "div.question-video-point-read"):
        #     logger.info("发现视频观看处理器")
        #     return VideoWatchHandler()
        from handler import find_handler_by_driver
        handler = find_handler_by_driver(driver)
        if handler:
            logger.info(f"发现处理器: {handler.__class__.__name__}")
            return handler
        logger.info("没有发现处理器处理本页")
        return None
    finally:
        if set_timeout:
            driver.implicitly_wait(1)
