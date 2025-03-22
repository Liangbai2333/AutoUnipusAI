from langchain_openai import ChatOpenAI

from util.config import config
from util.log import logger


def get_chat_model():
    logger.info(f"初始化大模型 {config['ai']['model']}")
    return ChatOpenAI(
        model=config['ai']['model'],
        api_key=config['ai']['openai_api_key'].strip(),
        base_url=config['ai']['openai_api_base'].strip()
    )

llm = get_chat_model()