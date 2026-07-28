"""
Subprocess command execution engine for queuectl.
Executes shell commands in a safe subprocess wrapper with timeout protection.
"""

import subprocess
import time
from dataclasses import dataclass
from typing import Optional
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.executor")


@dataclass
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


class CommandExecutor:
    @staticmethod
    def execute(command: str, timeout: Optional[float] = None) -> ExecutionResult:
        """
        Executes shell command string using subprocess.run().
        Returns ExecutionResult object detailing returncode, stdio output, and duration.
        """
        start_time = time.monotonic()
        try:
            completed_proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = time.monotonic() - start_time
            logger.info(
                f"Command completed in {duration:.2f}s with exit code {completed_proc.returncode}: '{command}'"
            )
            return ExecutionResult(
                exit_code=completed_proc.returncode,
                stdout=completed_proc.stdout,
                stderr=completed_proc.stderr,
                duration_seconds=duration,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start_time
            logger.error(f"Command timed out after {duration:.2f}s: '{command}'")
            return ExecutionResult(
                exit_code=-1,
                stdout=e.stdout or "",
                stderr=e.stderr or f"Command timed out after {timeout} seconds",
                duration_seconds=duration,
                timed_out=True,
            )
        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(f"Execution error running '{command}': {e}")
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=duration,
                timed_out=False,
            )
