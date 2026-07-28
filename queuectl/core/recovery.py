"""
Crash recovery service for queuectl.
Scans for orphaned or crashed jobs whose heartbeat is older than threshold (30 seconds)
and transitions them back to pending or dead (DLQ).
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List
from queuectl.database.db import get_connection
from queuectl.database.models import Job, utc_now_str
from queuectl.services.config_service import ConfigService
from queuectl.core.retry import get_next_retry_timestamp
from queuectl.utils.constants import (
    JobState,
    HEARTBEAT_THRESHOLD_SECONDS,
)
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.recovery")


class CrashRecoveryService:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path
        self.config_service = ConfigService(db_path)

    def recover_orphaned_jobs(self, threshold_seconds: int = HEARTBEAT_THRESHOLD_SECONDS) -> List[Job]:
        """
        Identifies processing jobs with heartbeat older than threshold_seconds.
        Recovers orphaned jobs by moving them to 'pending' with retry backoff,
        or to 'dead' if max retries have been reached.
        """
        now_dt = datetime.now(timezone.utc)
        cutoff_dt = now_dt - timedelta(seconds=threshold_seconds)
        cutoff_iso = cutoff_dt.isoformat()
        recovered_jobs: List[Job] = []

        backoff_base = self.config_service.get_backoff_base()

        with get_connection(self.db_path) as conn:
            # Query processing jobs where heartbeat or updated_at is stale
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE state = ?
                  AND (
                      (heartbeat IS NOT NULL AND heartbeat < ?)
                      OR (heartbeat IS NULL AND updated_at < ?)
                  );
                """,
                (JobState.PROCESSING.value, cutoff_iso, cutoff_iso),
            ).fetchall()

            for row in rows:
                job = Job.from_row(row)
                new_attempts = job.attempts + 1
                now_str = utc_now_str()

                if new_attempts >= job.max_retries:
                    # Exceeded max retries -> Move to Dead Letter Queue (DLQ)
                    new_state = JobState.DEAD.value
                    next_retry = None
                    logger.warning(
                        f"Recovering crashed job '{job.id}': attempts ({new_attempts}) reached max retries ({job.max_retries}). Moving to DLQ."
                    )
                else:
                    # Move back to pending state with retry backoff timestamp
                    new_state = JobState.PENDING.value
                    next_retry = get_next_retry_timestamp(new_attempts, backoff_base)
                    logger.warning(
                        f"Recovering crashed job '{job.id}': returning to PENDING state (attempt {new_attempts}/{job.max_retries}, next_retry: {next_retry})"
                    )

                conn.execute(
                    """
                    UPDATE jobs
                    SET state = ?,
                        attempts = ?,
                        next_retry_time = ?,
                        worker_id = NULL,
                        heartbeat = NULL,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (new_state, new_attempts, next_retry, now_str, job.id),
                )
                recovered_jobs.append(job)

        return recovered_jobs
