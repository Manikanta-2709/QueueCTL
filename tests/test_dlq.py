"""
Tests for Dead Letter Queue (DLQ) promotion and DLQ job retry resetting attempts to 0.
"""

import pytest
from pathlib import Path
from queuectl.services.job_service import JobService
from queuectl.core.worker import Worker
from queuectl.utils.constants import JobState


def test_dlq_promotion_after_max_retries(tmp_path: Path):
    db_file = tmp_path / "test_dlq.db"
    job_service = JobService(db_file)
    worker = Worker(db_file, worker_id="w-dlq")

    # Enqueue failing job with max_retries=1
    job_service.enqueue_job("job_dlq", "exit 1", max_retries=1)

    # Attempt 1 -> Fails and reaches max_retries
    job = worker.claim_job()
    worker.process_job(job)

    dlq_job = job_service.get_job("job_dlq")
    assert dlq_job.state == JobState.DEAD.value
    assert dlq_job.attempts == 1

    # Verify job appears in DLQ list
    dlq_list = job_service.list_dlq()
    assert len(dlq_list) == 1
    assert dlq_list[0].id == "job_dlq"


def test_dlq_retry_resets_attempts_to_zero(tmp_path: Path):
    db_file = tmp_path / "test_dlq_retry.db"
    job_service = JobService(db_file)
    worker = Worker(db_file, worker_id="w-dlq-retry")

    job_service.enqueue_job("dead_job", "exit 1", max_retries=1)
    job = worker.claim_job()
    worker.process_job(job)

    assert job_service.get_job("dead_job").state == JobState.DEAD.value

    # Retry DLQ job
    retried_job = job_service.retry_dlq_job("dead_job")
    assert retried_job.state == JobState.PENDING.value
    assert retried_job.attempts == 0
    assert retried_job.next_retry_time is None
    assert retried_job.worker_id is None
