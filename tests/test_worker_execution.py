"""
Tests for atomic worker job claim and command execution.
"""

import pytest
from pathlib import Path
from queuectl.services.job_service import JobService
from queuectl.core.worker import Worker
from queuectl.utils.constants import JobState


def test_worker_claim_and_execute_success(tmp_path: Path):
    db_file = tmp_path / "test_worker.db"
    job_service = JobService(db_file)
    worker = Worker(db_file, worker_id="test-worker-1")

    # Enqueue echo command
    job_service.enqueue_job("job1", "echo hello_worker")

    # Claim job
    claimed = worker.claim_job()
    assert claimed is not None
    assert claimed.id == "job1"
    assert claimed.state == JobState.PROCESSING.value
    assert claimed.worker_id == "test-worker-1"

    # Process job
    success = worker.process_job(claimed)
    assert success is True

    # Verify status in database
    job_after = job_service.get_job("job1")
    assert job_after.state == JobState.COMPLETED.value


def test_worker_claim_prevents_duplicate_reservation(tmp_path: Path):
    db_file = tmp_path / "test_dup_worker.db"
    job_service = JobService(db_file)
    worker1 = Worker(db_file, worker_id="w1")
    worker2 = Worker(db_file, worker_id="w2")

    job_service.enqueue_job("job_single", "echo single")

    claim1 = worker1.claim_job()
    claim2 = worker2.claim_job()

    assert claim1 is not None
    assert claim1.id == "job_single"
    assert claim2 is None  # Second worker gets None because job is already PROCESSING!
