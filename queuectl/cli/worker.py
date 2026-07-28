"""
CLI command module for worker pool lifecycle management.
Usage:
  queuectl worker start --count 3
  queuectl worker stop
"""

import click
from queuectl.core.scheduler import WorkerPoolManager
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.cli.worker")


@click.group(name="worker")
def worker_group():
    """Worker pool management commands."""
    pass


@worker_group.command(name="start")
@click.option("--count", default=3, type=int, help="Number of worker background processes to start.")
def worker_start_cmd(count: int):
    """Starts background worker process pool."""
    if count <= 0:
        click.echo("Error: Worker count must be greater than 0.", err=True)
        raise click.Abort()

    manager = WorkerPoolManager()
    pids = manager.start_workers(count=count)
    click.echo(f"Started {count} worker processes (PIDs: {pids}).")


@worker_group.command(name="stop")
def worker_stop_cmd():
    """Stops all running background worker processes gracefully."""
    stopped_pids = WorkerPoolManager.stop_workers()
    if stopped_pids:
        click.echo(f"Worker pool stopped gracefully. (PIDs terminated: {stopped_pids})")
    else:
        click.echo("No running worker pool process found.")


import signal

@worker_group.command(name="run")
@click.option("--worker-id", default=None, type=str, help="Custom ID for this worker process.")
def worker_run_cmd(worker_id: str | None):
    """Runs a single worker process in the foreground (ideal for Docker & Cloud containers)."""
    from queuectl.core.worker import Worker
    worker = Worker(worker_id=worker_id)

    def _handle_signal(signum, frame):
        logger.info(f"Worker '{worker.worker_id}' received signal {signum}. Initiating graceful exit...")
        worker.stop_requested = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    click.echo(f"Starting worker process '{worker.worker_id}' in foreground...")
    worker.run_forever()


