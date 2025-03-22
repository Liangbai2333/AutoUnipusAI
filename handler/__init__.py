from typing import Self

from selenium.webdriver.chrome.webdriver import WebDriver

from handler.types import *


# 简单的路由实现.
class __Registry:
    def __init__(self, handler: BaseHandler):
        self.to_targets = []
        self.not_to_targets = []
        self.handler = handler

    def to(self, *targets: str) -> Self:
        self.to_targets.extend(targets)
        return self

    def not_to(self, *targets: str) -> Self:
        self.not_to_targets.extend(targets)
        return self


registered_handlers: list[__Registry] = []

def register_handler(handler: BaseHandler) -> __Registry:
    registry = __Registry(handler)
    registered_handlers.append(registry)
    return registry

register_handler(DiscussionHandler()).to("div.layout-container.discussion-view")
register_handler(AudioWithBlankFillingHandler()).to("div.audio-material-wrapper", "div.comp-scoop-reply").not_to("div.comp-scoop-reply-dropdown-selection-overflow")
register_handler(AudioWithChoiceHandler()).to("div.audio-material-wrapper", "div.question-common-abs-choice")
register_handler(VideoWithBlankFillingHandler()).to("div.video-material-wrapper", "div.comp-scoop-reply").not_to("div.comp-scoop-reply-dropdown-selection-overflow")
register_handler(VideoWithChoiceHandler()).to("div.video-material-wrapper", "div.question-common-abs-choice")
register_handler(ArticleWithChoiceHandler()).to("div.text-material-wrapper", "div.question-common-abs-choice")
register_handler(IdeaWithAudioOrVideoHandler()).to("div.audio-material-wrapper", "div.question-inputbox")
register_handler(IdeaWithAudioOrVideoHandler()).to("div.video-material-wrapper", "div.question-inputbox")
register_handler(IdeaWithArticleHandler()).to("div.text-material-wrapper", "div.question-inputbox")
register_handler(WordCorrectionHandler()).to("div.layout-reply-container.full", "div.comp-scoop-reply")
register_handler(VideoWatchHandler()).to("div.question-video-point-read")
register_handler(AudioDragElementHandler()).to("div.audio-material-wrapper", "div.sortable-list-wrapper")
register_handler(VideoDragElementHandler()).to("div.video-material-wrapper", "div.sortable-list-wrapper")
register_handler(AudioSelectionHandler()).to("div.audio-material-wrapper", "div.comp-scoop-reply-dropdown-selection-overflow")
register_handler(VideoSelectionHandler()).to("div.video-material-wrapper", "div.comp-scoop-reply-dropdown-selection-overflow")

def find_handler_by_driver(source: WebDriver) -> Optional[BaseHandler]:
    for registry in registered_handlers:
        if all([find_element_safely(source, target) for target in registry.to_targets]) \
                and not any([find_element_safely(source, target) for target in registry.not_to_targets]):
            return registry.handler

    return None

