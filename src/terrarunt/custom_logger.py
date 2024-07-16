import logging
import os


class Logger(logging.Logger):
    def __init__(self, name):
        level = os.getenv("LOG_LEVEL", "INFO")
        super().__init__(name, level)
