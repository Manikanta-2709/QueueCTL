"""
Worker core component for queuectl.
Performs atomic job reservations, heartbeat updates, subprocess execution,
and retry/DLQ database state transitions.
"""

import os
import time
import threading
import uuid
from pathlib import Path
from typing import Optional
import sqlite3

from queuectl.database.db import get_connection
from queuectl.database.models import Job, utc_now_str
from queuectl.services.config_service import ConfigService
from queuectl.core.executor import CommandExecutor
from queuectl.core.retry import get_next_retry_timestamp
from queuectl.utils.constants import (
    JobState,
    HEARTBEAT_INTERVAL_SECONDS,
)
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.worker")


class HeartbeatLoop(threading.Thread):
    """Background daemon thread that continuously updates the heartbeat timestamp for an active job."""

    def __init__(self, db_path: Optional[Path], job_id: str, interval: float = HEARTBEAT_INTERVAL_SECONDS):
        super().__init__(daemon=True)
        self.db_path = db_path
        self.job_id = job_id
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            time.sleep(self.interval)
            if self.stop_event.is_set():
                break
            self._send_heartbeat()

    def _send_heartbeat(self):
        now_str = utc_now_str()
        try:
            with get_connection(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET heartbeat = ?, updated_at = ?
                    WHERE id = ? AND state = ?;
                    """,
                    (now_str, now_str, self.job_id, JobState.PROCESSING.value),
                )
        except Exception as e:
            logger.error(f"Heartbeat update failed for job '{self.job_id}': {e}")

    def stop(self):
        self.stop_event.set()


class Worker:
    def __init__(self, db_path: Optional[Path] = None, worker_id: Optional[str] = None):
        self.db_path = db_path
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.config_service = ConfigService(db_path)
        self.stop_requested = False

    def claim_job(self) -> Optional[Job]:
        """
        Atomically claims a single pending job using an IMMEDIATE transaction block.
        Ensures strict process-safety so no two workers reserve the same job.
        """
        now_str = utc_now_str()
        with get_connection(self.db_path) as conn:
            # Begin immediate write lock to guarantee atomicity across processes
            conn.execute("BEGIN IMMEDIATE;")
            
            # Find eligible pending job where next_retry_time is reached or NULL
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE state = ?
                  AND (next_retry_time IS NULL OR next_retry_time <= ?)
                ORDER BY created_at ASC
                LIMIT 1;
                """,
                (JobState.PENDING.value, now_str),
            ).fetchone()

            if not row:
                return None

            job_id = row["id"]

            # Atomically update state to PROCESSING
            conn.execute(
                """
                UPDATE jobs
                SET state = ?,
                    worker_id = ?,
                    heartbeat = ?,
                    updated_at = ?
                WHERE id = ? AND state = ?;
                """,
                (
                    JobState.PROCESSING.value,
                    self.worker_id,
                    now_str,
                    now_str,
                    job_id,
                    JobState.PENDING.value,
                ),
            )

            # Retrieve updated job record
            updated_row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?;", (job_id,)
            ).fetchone()

            if updated_row:
                job = Job.from_row(updated_row)
                logger.info(f"Worker '{self.worker_id}' claimed job '{job.id}'")
                return job

        return None

    def process_job(self, job: Job) -> bool:
        """
        Executes job command in subprocess while maintaining background heartbeat.
        Updates job status to 'completed', 'pending' (retry), or 'dead' (DLQ).
        """
        logger.info(f"Worker '{self.worker_id}' started processing job '{job.id}'")
        
        # Start heartbeat background thread
        heartbeat_thread = HeartbeatLoop(self.db_path, job.id)
        heartbeat_thread.start()

        try:
            result = CommandExecutor.execute(job.command)
        finally:
            heartbeat_thread.stop()

        now_str = utc_now_str()
        backoff_base = self.config_service.get_backoff_base()

        with get_connection(self.db_path) as conn:
            if result.exit_code == 0:
                # Execution Success
                conn.execute(
                    """
                    UPDATE jobs
                    SET state = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (JobState.COMPLETED.value, now_str, job.id),
                )
                logger.info(f"Worker '{self.worker_id}' completed job '{job.id}' successfully.")
                return True
            else:
                # Execution Failure -> Calculate Retries & Exponential Backoff
                new_attempts = job.attempts + 1
                if new_attempts >= job.max_retries:
                    # Move to Dead Letter Queue (DLQ)
                    conn.execute(
                        """
                        UPDATE jobs
                        SET state = ?,
                            attempts = ?,
                            next_retry_time = NULL,
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (JobState.DEAD.value, new_attempts, now_str, job.id),
                    )
                    logger.warning(
                        f"Job '{job.id}' failed (exit code {result.exit_code}). Reached max retries ({job.max_retries}). Moved to DLQ."
                    )
                else:
                    # Schedule Retry with Exponential Backoff
                    next_retry_iso = get_next_retry_timestamp(new_attempts, backoff_base)
                    conn.execute(
                        """
                        UPDATE jobs
                        SET state = ?,
                            attempts = ?,
                            next_retry_time = ?,
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (
                            JobState.PENDING.value,
                            new_attempts,
                            next_retry_iso,
                            now_str,
                            job.id,
                        ),
                    )
                    logger.warning(
                        f"Job '{job.id}' failed (exit code {result.exit_code}). Scheduled retry #{new_attempts} for {next_retry_iso}."
                    )
                return False

    def run_single_loop(self) -> bool:
        """Claims and processes a single job if available. Returns True if a job was processed."""
        job = self.claim_job()
        if job:
            self.process_job(job)
            return True
        return False

    def run_forever(self, poll_interval: float = 1.0):
        """Main worker loop. Continuously claims and processes jobs until stop is requested."""
        logger.info(f"Worker process '{self.worker_id}' started.")
        while not self.stop_requested:
            processed = self.run_single_loop()
            if not processed:
                time.sleep(poll_interval)
        logger.info(f"Worker process '{self.worker_id}' stopped gracefully.")
