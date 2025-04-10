import logging
from logging.handlers import RotatingFileHandler
import os


def get_logger(name="terrarunt", log_file=None):
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger  # Avoid adding handlers multiple times

    logger.setLevel(logging.DEBUG)

    log_file = log_file or os.getenv("TF_WRAPPER_LOG_FILE", "terrarunt.log")

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False

    return logger