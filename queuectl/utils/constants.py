"""
Application-wide constants and configuration defaults for queuectl.
"""

from enum import Enum
import os
from pathlib import Path


class JobState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


# Configuration keys stored in system config table
CONFIG_MAX_RETRIES_KEY = "max-retries"
CONFIG_BACKOFF_BASE_KEY = "backoff-base"

# System default values
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2.0

# Worker and Heartbeat timing thresholds (seconds)
HEARTBEAT_INTERVAL_SECONDS = 5
HEARTBEAT_THRESHOLD_SECONDS = 30
RECOVERY_INTERVAL_SECONDS = 10

DEFAULT_DATA_DIR = Path.home() / ".queuectl"

def get_default_db_path() -> Path:
    return Path(os.getenv("QUEUECTL_DB_PATH", str(DEFAULT_DATA_DIR / "queue.db")))


def get_default_log_dir() -> Path:
    return Path(os.getenv("QUEUECTL_LOG_DIR", str(DEFAULT_DATA_DIR / "logs")))

def get_default_pid_file() -> Path:
    return Path(os.getenv("QUEUECTL_PID_FILE", str(DEFAULT_DATA_DIR / "workers.pid")))

DEFAULT_DB_PATH = get_default_db_path()
DEFAULT_LOG_DIR = get_default_log_dir()
DEFAULT_PID_FILE = get_default_pid_file()

