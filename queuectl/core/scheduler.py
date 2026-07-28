"""
Scheduler and process pool manager for queuectl.
Spawns background worker processes, manages PID tracking files,
and executes background crash recovery polling loops.
"""

import json
import os
import signal
import sys
import time
import multiprocessing
from pathlib import Path
from typing import List, Optional

from queuectl.core.worker import Worker
from queuectl.core.recovery import CrashRecoveryService
from queuectl.utils.constants import DEFAULT_PID_FILE, RECOVERY_INTERVAL_SECONDS
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.scheduler")


def _worker_process_entrypoint(db_path_str: Optional[str], worker_name: str):
    """Entrypoint executed inside child multiprocessing Worker process."""
    db_path = Path(db_path_str) if db_path_str else None
    worker = Worker(db_path=db_path, worker_id=worker_name)

    # Signal handlers for graceful shutdown
    def _handle_signal(signum, frame):
        logger.info(f"Worker '{worker_name}' received signal {signum}. Initiating graceful exit...")
        worker.stop_requested = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    worker.run_forever()


def _recovery_process_entrypoint(db_path_str: Optional[str]):
    """Entrypoint executed inside background Crash Recovery process."""
    db_path = Path(db_path_str) if db_path_str else None
    recovery_service = CrashRecoveryService(db_path)
    stop_event = threading_event = False

    logger.info("Background Crash Recovery Service process started.")
    try:
        while True:
            try:
                recovered = recovery_service.recover_orphaned_jobs()
                if recovered:
                    logger.info(f"Recovery service restored {len(recovered)} orphaned jobs.")
            except Exception as e:
                logger.error(f"Error during crash recovery scan: {e}")
            time.sleep(RECOVERY_INTERVAL_SECONDS)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Background Crash Recovery Service process exiting.")


class PIDFileManager:
    """Manages recording and reading worker process IDs to disk for cross-terminal management."""

    @staticmethod
    def save_pids(pids: List[int], pid_file: Path = DEFAULT_PID_FILE):
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"pids": pids, "timestamp": time.time()}
        with open(pid_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @staticmethod
    def load_pids(pid_file: Path = DEFAULT_PID_FILE) -> List[int]:
        if not pid_file.exists():
            return []
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("pids", [])
        except Exception:
            return []

    @staticmethod
    def clear_pids(pid_file: Path = DEFAULT_PID_FILE):
        if pid_file.exists():
            try:
                pid_file.unlink()
            except Exception:
                pass


class WorkerPoolManager:
    def __init__(self, db_path: Optional[Path] = None, pid_file: Path = DEFAULT_PID_FILE):
        self.db_path = db_path
        self.pid_file = pid_file

    def start_workers(self, count: int = 3) -> List[int]:
        """Spawns specified count of worker processes and records their PIDs to disk."""
        ctx = multiprocessing.get_context("spawn")
        processes: List[multiprocessing.Process] = []
        pids: List[int] = []

        db_str = str(self.db_path) if self.db_path else None

        for i in range(count):
            worker_name = f"worker-proc-{i+1}"
            p = ctx.Process(
                target=_worker_process_entrypoint,
                args=(db_str, worker_name),
                daemon=True,
            )
            p.start()
            processes.append(p)
            if p.pid:
                pids.append(p.pid)

        # Also start background recovery process
        rec_p = ctx.Process(
            target=_recovery_process_entrypoint,
            args=(db_str,),
            daemon=True,
        )
        rec_p.start()
        if rec_p.pid:
            pids.append(rec_p.pid)

        PIDFileManager.save_pids(pids, self.pid_file)
        logger.info(f"Started {count} worker processes and 1 recovery service process (PIDs: {pids})")
        return pids

    @staticmethod
    def stop_workers(pid_file: Path = DEFAULT_PID_FILE) -> List[int]:
        """
        Reads running worker PIDs from disk and sends SIGTERM for graceful shutdown.
        On Windows, uses taskkill or os.kill.
        """
        pids = PIDFileManager.load_pids(pid_file)
        if not pids:
            return []

        stopped_pids = []
        for pid in pids:
            try:
                if sys.platform == "win32":
                    os.kill(pid, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
                stopped_pids.append(pid)
            except OSError:
                # Process already terminated
                pass

        PIDFileManager.clear_pids(pid_file)
        logger.info(f"Stopped worker processes: {stopped_pids}")
        return stopped_pids
