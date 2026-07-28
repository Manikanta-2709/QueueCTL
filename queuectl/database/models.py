"""
Data models and schemas for queuectl.
Defines the Job dataclass and conversion helpers.
"""

import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from queuectl.utils.constants import JobState, DEFAULT_MAX_RETRIES


def utc_now_str() -> str:
    """Returns current UTC timestamp formatted as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    command: str
    state: str = JobState.PENDING.value
    attempts: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    created_at: str = field(default_factory=utc_now_str)
    updated_at: str = field(default_factory=utc_now_str)
    worker_id: Optional[str] = None
    heartbeat: Optional[str] = None
    next_retry_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts Job instance to dictionary suitable for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row | tuple | dict) -> "Job":
        """Constructs a Job instance from a SQLite row dictionary or tuple."""
        if isinstance(row, dict) or hasattr(row, "keys"):
            d = dict(row)
            return cls(
                id=d["id"],
                command=d["command"],
                state=d["state"],
                attempts=d["attempts"],
                max_retries=d["max_retries"],
                created_at=d["created_at"],
                updated_at=d["updated_at"],
                worker_id=d.get("worker_id"),
                heartbeat=d.get("heartbeat"),
                next_retry_time=d.get("next_retry_time"),
            )
        return cls(
            id=row[0],
            command=row[1],
            state=row[2],
            attempts=row[3],
            max_retries=row[4],
            created_at=row[5],
            updated_at=row[6],
            worker_id=row[7],
            heartbeat=row[8],
            next_retry_time=row[9],
        )

