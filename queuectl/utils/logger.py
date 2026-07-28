"""
Centralized logging utility for queuectl.
Appends formatted worker logs to logs/worker.log with millisecond timestamps.
"""

import logging
import sys
from pathlib import Path
from queuectl.utils.constants import DEFAULT_LOG_DIR


def get_logger(name: str = "queuectl") -> logging.Logger:
    """
    Returns a configured logger with console and file handlers.
    Creates log directory if it does not exist.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    log_format = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(processName)s:%(threadName)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Ensure log directory exists
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file_path = DEFAULT_LOG_DIR / "worker.log"

    # File Handler (Worker log persistent output)
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    # Stream Handler (CLI stdout / stderr debug logging)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.WARNING)
    stream_handler.setFormatter(log_format)
    logger.addHandler(stream_handler)

    return logger
