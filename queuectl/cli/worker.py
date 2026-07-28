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
