"""
Database connection management and initialization module for queuectl.
Configures SQLite in Write-Ahead Logging (WAL) mode for multi-process safety.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from queuectl.utils.constants import (
    get_default_db_path,
    DEFAULT_MAX_RETRIES,
    DEFAULT_BACKOFF_BASE,
    CONFIG_MAX_RETRIES_KEY,
    CONFIG_BACKOFF_BASE_KEY,
)
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.db")


def get_db_path() -> Path:
    """Returns absolute Path to the SQLite database file."""
    return get_default_db_path()



@contextmanager
def get_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager yielding a thread/process safe SQLite connection.
    Enforces WAL journal mode, busy timeout, and automatic commit/rollback.
    """
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Performance & Concurrency PRAGMAs
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction error: {e}")
        raise e
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    """
    Initializes jobs and config tables and sets up performance indexes.
    Populates system default configs if not already present.
    """
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                worker_id TEXT,
                heartbeat TEXT,
                next_retry_time TEXT
            );
            """
        )

        # Index for high-throughput atomic claims filtering on state and next_retry_time
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jobs_state_retry 
            ON jobs (state, next_retry_time, created_at);
            """
        )

        # Key-Value configuration store
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        # Seed default configurations if missing
        conn.execute(
            """
            INSERT OR IGNORE INTO config (key, value)
            VALUES (?, ?);
            """,
            (CONFIG_MAX_RETRIES_KEY, str(DEFAULT_MAX_RETRIES)),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO config (key, value)
            VALUES (?, ?);
            """,
            (CONFIG_BACKOFF_BASE_KEY, str(DEFAULT_BACKOFF_BASE)),
        )

        logger.info(f"Database initialized successfully at {db_path or get_db_path()}")
