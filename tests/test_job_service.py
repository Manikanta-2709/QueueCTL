"""
Tests for JobService and ConfigService operations.
"""

import pytest
from pathlib import Path
from queuectl.services.job_service import JobService
from queuectl.services.config_service import ConfigService
from queuectl.utils.constants import JobState, DEFAULT_MAX_RETRIES, DEFAULT_BACKOFF_BASE


def test_config_service_defaults_and_override(tmp_path: Path):
    db_file = tmp_path / "test_config.db"
    config_service = ConfigService(db_file)

    assert config_service.get_max_retries() == DEFAULT_MAX_RETRIES
    assert config_service.get_backoff_base() == DEFAULT_BACKOFF_BASE

    config_service.set_config("max-retries", "5")
    config_service.set_config("backoff-base", "3.5")

    assert config_service.get_max_retries() == 5
    assert config_service.get_backoff_base() == 3.5


def test_enqueue_and_get_job(tmp_path: Path):
    db_file = tmp_path / "test_job.db"
    job_service = JobService(db_file)

    job = job_service.enqueue_job("job1", "echo hello")
    assert job.id == "job1"
    assert job.command == "echo hello"
    assert job.state == JobState.PENDING.value

    retrieved = job_service.get_job("job1")
    assert retrieved is not None
    assert retrieved.id == "job1"


def test_enqueue_duplicate_job_raises(tmp_path: Path):
    db_file = tmp_path / "test_job_dup.db"
    job_service = JobService(db_file)

    job_service.enqueue_job("job1", "echo hello")
    with pytest.raises(ValueError, match="already exists"):
        job_service.enqueue_job("job1", "echo world")


def test_status_counts(tmp_path: Path):
    db_file = tmp_path / "test_status.db"
    job_service = JobService(db_file)

    job_service.enqueue_job("j1", "cmd1")
    job_service.enqueue_job("j2", "cmd2")

    counts = job_service.get_status_counts()
    assert counts["pending"] == 2
    assert counts["processing"] == 0
    assert counts["completed"] == 0
    assert counts["failed"] == 0
    assert counts["dead"] == 0
