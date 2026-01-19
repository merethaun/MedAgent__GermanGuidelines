import logging
import os

LOG_FILE_PATH = os.getenv("BACKEND_LOG__FILE_PATH", "src/logs/backend/backend.log")  # resolves to logs/backend/backend.log
LOG_FILE_MAX_SIZE_MB = os.getenv("BACKEND_LOG__FILE_MAX_SIZE_MB", 10)
LOG_FILE_BACKUP_COUNT = os.getenv("BACKEND_LOG__FILE_BACKUP_COUNT", 5)
LOG_LEVEL_CONSOLE = logging.DEBUG
LOG_LEVEL_FILE = logging.DEBUG
