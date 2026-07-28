"""
Tests for retry backoff calculations, retry scheduling, and DLQ transition.
"""

import pytest
from pathlib import Path
from queuectl.core.retry import calculate_backoff_delay
from queuectl.services.job_service import JobService
from queuectl.core.worker import Worker
from queuectl.utils.constants import JobState


def test_calculate_backoff_delay():
    # Formula: base ^ attempts
    assert calculate_backoff_delay(1, base=2.0) == 2.0
    assert calculate_backoff_delay(2, base=2.0) == 4.0
    assert calculate_backoff_delay(3, base=2.0) == 8.0

    # Custom base
    assert calculate_backoff_delay(1, base=3.0) == 3.0
    assert calculate_backoff_delay(2, base=3.0) == 9.0


def test_failed_command_triggers_retry(tmp_path: Path):
    db_file = tmp_path / "test_retry.db"
    job_service = JobService(db_file)
    worker = Worker(db_file, worker_id="w-retry")

    # Enqueue a failing command with max_retries=3
    job_service.enqueue_job("fail1", "exit 1", max_retries=3)

    # Claim & Process Attempt 1
    job = worker.claim_job()
    success = worker.process_job(job)

    assert success is False
    job_after_1 = job_service.get_job("fail1")
    assert job_after_1.state == JobState.PENDING.value
    assert job_after_1.attempts == 1
    assert job_after_1.next_retry_time is not None
