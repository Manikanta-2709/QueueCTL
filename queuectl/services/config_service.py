"""
Config Service managing system settings (max-retries, backoff-base) stored in SQLite.
"""

from pathlib import Path
from queuectl.database.db import get_connection, init_db
from queuectl.utils.constants import (
    CONFIG_MAX_RETRIES_KEY,
    CONFIG_BACKOFF_BASE_KEY,
    DEFAULT_MAX_RETRIES,
    DEFAULT_BACKOFF_BASE,
)


class ConfigService:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path
        init_db(self.db_path)

    def get_config(self, key: str, default: str) -> str:
        """Retrieves configuration string by key from the database."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?;", (key,)
            ).fetchone()
            if row:
                return row["value"]
            return default

    def set_config(self, key: str, value: str) -> None:
        """Sets or updates configuration key-value pair in SQLite."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                """,
                (key, str(value)),
            )

    def get_max_retries(self) -> int:
        """Returns max retries as an integer."""
        val = self.get_config(CONFIG_MAX_RETRIES_KEY, str(DEFAULT_MAX_RETRIES))
        try:
            return int(val)
        except ValueError:
            return DEFAULT_MAX_RETRIES

    def get_backoff_base(self) -> float:
        """Returns backoff base as a float."""
        val = self.get_config(CONFIG_BACKOFF_BASE_KEY, str(DEFAULT_BACKOFF_BASE))
        try:
            return float(val)
        except ValueError:
            return DEFAULT_BACKOFF_BASE
