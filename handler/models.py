from typing import Optional

from pydantic import BaseModel, Field

class Choice(BaseModel):
    caption: str
    content: str
class BaseSingleChoice(BaseModel):
    caption: str
class BaseMultipleChoice(BaseModel):
    captions: list[str]
class DiscussionAnswer(BaseModel):
    answer: str
class ChoiceAnswer(BaseModel):
    single_choices: Optional[list[BaseSingleChoice]] = Field(default=None, description="顺序返回的单选题的答案选择集合, 没有则返回空集合")
    multiple_choices: Optional[list[BaseMultipleChoice]] = Field(default=None, description="顺序返回的多选题的答案选择集合, 没有则返回空集合")
class AudioWithBlankFillingAnswer(BaseModel):
    blanks: list[str]
class VideoWithBlankFillingAnswer(BaseModel):
    blanks: list[str]
class IdeaWithAudioOrVideoAnswer(BaseModel):
    answers: list[str]
class WordCorrectionAnswer(BaseModel):
    blanks: list[str]
class IdeaWithPassageAnswer(BaseModel):
    answers: list[str]

class DragElementAnswer(BaseModel):
    orders: list[int] = Field(default=[], description="顺序返回的拖拽元素的答案顺序集合")

class SelectionAnswer(BaseModel):
    captions: list[int] = Field(default=[], description="选择题的答案序号集合")