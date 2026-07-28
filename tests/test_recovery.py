"""
Tests for CrashRecoveryService reclaiming orphaned processing jobs.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from queuectl.database.db import get_connection
from queuectl.services.job_service import JobService
from queuectl.core.worker import Worker
from queuectl.core.recovery import CrashRecoveryService
from queuectl.utils.constants import JobState


def test_crash_recovery_reclaims_stale_heartbeat_job(tmp_path: Path):
    db_file = tmp_path / "test_recovery.db"
    job_service = JobService(db_file)
    worker = Worker(db_file, worker_id="crashed-worker")
    recovery_service = CrashRecoveryService(db_file)

    job_service.enqueue_job("crashed_job", "sleep 100", max_retries=3)
    job = worker.claim_job()
    assert job.state == JobState.PROCESSING.value

    # Simulate worker crash by setting heartbeat to 40 seconds in the past
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=40)).isoformat()
    with get_connection(db_file) as conn:
        conn.execute(
            "UPDATE jobs SET heartbeat = ? WHERE id = ?;", (stale_time, job.id)
        )

    # Run crash recovery check with 30s threshold
    recovered_jobs = recovery_service.recover_orphaned_jobs(threshold_seconds=30)
    assert len(recovered_jobs) == 1
    assert recovered_jobs[0].id == "crashed_job"

    # Verify state in database restored to pending with incremented attempt
    rec_job_db = job_service.get_job("crashed_job")
    assert rec_job_db.state == JobState.PENDING.value
    assert rec_job_db.attempts == 1
    assert rec_job_db.worker_id is None
