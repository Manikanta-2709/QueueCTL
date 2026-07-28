"""
CLI command module for system status overview.
Usage: queuectl status
"""

import click
from queuectl.services.job_service import JobService
from queuectl.core.scheduler import PIDFileManager
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.cli.status")


@click.command(name="status")
def status_cmd():
    """Displays job queue breakdown and worker status summary."""
    job_service = JobService()
    counts = job_service.get_status_counts()
    active_pids = PIDFileManager.load_pids()

    click.echo("\n--- Queuectl System Status ---")
    click.echo(f"Pending    : {counts.get('pending', 0)}")
    click.echo(f"Processing : {counts.get('processing', 0)}")
    click.echo(f"Completed  : {counts.get('completed', 0)}")
    click.echo(f"Failed     : {counts.get('failed', 0)}")
    click.echo(f"Dead (DLQ) : {counts.get('dead', 0)}")
    click.echo(f"Workers    : {len(active_pids)} active processes (PIDs: {active_pids})")
    click.echo("-----------------------------\n")
