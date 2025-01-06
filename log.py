import logging

from config import config


def setup_logger():
    logging.basicConfig(
        level=config['logging']['level'],
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config['logging']['file']),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger()


logger = setup_logger()