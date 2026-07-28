"""
Job Service providing business operations for job submission, querying, DLQ management, and status aggregation.
"""

from pathlib import Path
from typing import List, Dict, Optional
import sqlite3
from queuectl.database.db import get_connection, init_db
from queuectl.database.models import Job, utc_now_str
from queuectl.services.config_service import ConfigService
from queuectl.utils.constants import JobState
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.job_service")


class JobService:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path
        self.config_service = ConfigService(db_path)
        init_db(self.db_path)

    def enqueue_job(self, job_id: str, command: str, max_retries: Optional[int] = None) -> Job:
        """
        Creates and enqueues a new job into SQLite database.
        If max_retries is not specified, uses system default config.
        """
        if not job_id or not job_id.strip():
            raise ValueError("Job ID cannot be empty.")
        if not command or not command.strip():
            raise ValueError("Job command cannot be empty.")

        effective_max_retries = (
            max_retries if max_retries is not None else self.config_service.get_max_retries()
        )

        job = Job(
            id=job_id.strip(),
            command=command.strip(),
            state=JobState.PENDING.value,
            attempts=0,
            max_retries=effective_max_retries,
        )

        with get_connection(self.db_path) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO jobs (id, command, state, attempts, max_retries, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        job.id,
                        job.command,
                        job.state,
                        job.attempts,
                        job.max_retries,
                        job.created_at,
                        job.updated_at,
                    ),
                )
                logger.info(f"Enqueued job '{job.id}' (command: '{job.command}')")
            except sqlite3.IntegrityError:
                raise ValueError(f"Job with ID '{job.id}' already exists.")

        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieves job by ID."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?;", (job_id,)
            ).fetchone()
            if row:
                return Job.from_row(row)
            return None

    def list_jobs(self, state: Optional[str] = None) -> List[Job]:
        """Lists jobs filtered optionally by state."""
        with get_connection(self.db_path) as conn:
            if state:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE state = ? ORDER BY created_at ASC;",
                    (state,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at ASC;"
                ).fetchall()
            return [Job.from_row(row) for row in rows]

    def get_status_counts(self) -> Dict[str, int]:
        """Returns aggregate count of jobs grouped by state."""
        counts = {s.value: 0 for s in JobState}
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT state, COUNT(*) as cnt FROM jobs GROUP BY state;"
            ).fetchall()
            for r in rows:
                if r["state"] in counts:
                    counts[r["state"]] = r["cnt"]
        return counts

    def list_dlq(self) -> List[Job]:
        """Lists all Dead Letter Queue jobs (state = 'dead')."""
        return self.list_jobs(state=JobState.DEAD.value)

    def retry_dlq_job(self, job_id: str) -> Job:
        """
        Retries a dead-lettered job by resetting state to 'pending',
        attempts counter to 0, and clearing next_retry_time and worker_id.
        """
        now = utc_now_str()
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?;", (job_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Job '{job_id}' not found.")
            
            job = Job.from_row(row)
            if job.state != JobState.DEAD.value:
                raise ValueError(f"Job '{job_id}' is in '{job.state}' state, not 'dead'.")

            conn.execute(
                """
                UPDATE jobs
                SET state = ?, attempts = 0, next_retry_time = NULL, worker_id = NULL, heartbeat = NULL, updated_at = ?
                WHERE id = ?;
                """,
                (JobState.PENDING.value, now, job_id),
            )
            logger.info(f"Reset dead job '{job_id}' to pending state with attempts=0")

        return self.get_job(job_id)
