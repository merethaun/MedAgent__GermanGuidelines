import os
import sys
import time
from logging.handlers import RotatingFileHandler

from app.constants.logging_settings import *


def setup_logger(name: str = None, log_to_console: bool = True, level=logging.DEBUG) -> logging.Logger:
    """
    Sets up and returns a logger with both console and rotating file handlers.
    - Utilization: below import, call logger=setup_logger(__name__) or similar
    - Can test by calling logger.debug("Logging initialized")
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # avoid duplicate handlers
    
    logger.setLevel(level)
    
    # Write to the console
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(LOG_LEVEL_CONSOLE)
        console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console_formatter.converter = time.gmtime
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # Write to a file
    os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE_PATH, maxBytes=int(LOG_FILE_MAX_SIZE_MB * 1024 * 1024), backupCount=LOG_FILE_BACKUP_COUNT,
    )
    file_handler.setLevel(LOG_LEVEL_FILE)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_formatter.converter = time.gmtime
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger
