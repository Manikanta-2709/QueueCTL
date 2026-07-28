"""
Tests for database initialization, connection handling, and Job model serialization.
"""

import pytest
from pathlib import Path
from queuectl.database.db import init_db, get_connection
from queuectl.database.models import Job
from queuectl.utils.constants import JobState


def test_init_db_creates_tables(tmp_path: Path):
    db_file = tmp_path / "test_queue.db"
    init_db(db_file)

    assert db_file.exists()

    with get_connection(db_file) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "jobs" in table_names
        assert "config" in table_names


def test_job_model_conversion():
    job = Job(id="job_test_1", command="echo test")
    assert job.state == JobState.PENDING.value
    assert job.attempts == 0

    d = job.to_dict()
    assert d["id"] == "job_test_1"
    assert d["command"] == "echo test"

    reconstructed = Job.from_row(d)
    assert reconstructed.id == job.id
    assert reconstructed.command == job.command
