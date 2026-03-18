import logging
import os
from pathlib import Path

def _default_log_file_path() -> str:
    container_logs = Path("/logs")
    if container_logs.exists():
        return str(container_logs / "backend.log")

    backend_root = Path(__file__).resolve().parents[3]
    repo_root = backend_root.parent
    return str(repo_root / "logs" / "backend" / "backend.log")

LOG_FILE_PATH = os.getenv("BACKEND_LOG__FILE_PATH", _default_log_file_path())
LOG_FILE_MAX_SIZE_MB = os.getenv("BACKEND_LOG__FILE_MAX_SIZE_MB", 10)
LOG_FILE_BACKUP_COUNT = os.getenv("BACKEND_LOG__FILE_BACKUP_COUNT", 5)
LOG_LEVEL_CONSOLE = logging.DEBUG
LOG_LEVEL_FILE = logging.DEBUG
