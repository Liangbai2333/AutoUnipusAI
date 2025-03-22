import logging
import os.path

from util.config import config

def setup_logger():
    file = config['logging']['file']

    if not os.path.isfile(file):
        os.makedirs(os.path.dirname(file), exist_ok=True)
        with open(file, 'w') as f:
            f.write('')


    logging.basicConfig(
        level=config['logging']['level'],
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger()


logger = setup_logger()