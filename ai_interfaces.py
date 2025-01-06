import os

import yaml
from langchain_openai import ChatOpenAI

from log import logger


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yml")
    with open(config_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)

config = load_config()

def get_chat_model():
    logger.info(f"初始化大模型 {config['ai']['model']}")
    return ChatOpenAI(
        model=config['ai']['model'],
        openai_api_key=config['ai']['openai_api_key'],
        openai_api_base=config['ai']['openai_api_base']
    )

chat = get_chat_model()