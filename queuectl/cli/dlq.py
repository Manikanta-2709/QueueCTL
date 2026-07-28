"""
CLI command module for Dead Letter Queue (DLQ) operations.
Usage:
  queuectl dlq list
  queuectl dlq retry job1
"""

import click
from queuectl.services.job_service import JobService


@click.group(name="dlq")
def dlq_group():
    """Dead Letter Queue (DLQ) management commands."""
    pass


@dlq_group.command(name="list")
def dlq_list_cmd():
    """Lists all dead-lettered jobs."""
    job_service = JobService()
    dead_jobs = job_service.list_dlq()

    if not dead_jobs:
        click.echo("Dead Letter Queue (DLQ) is empty.")
        return

    click.echo(f"\n--- Dead Letter Queue ({len(dead_jobs)} jobs) ---")
    click.echo("-" * 80)
    click.echo(f"{'ID':<15} {'ATTEMPTS':<10} {'COMMAND':<30} {'UPDATED AT'}")
    click.echo("-" * 80)
    for j in dead_jobs:
        cmd_trunc = (j.command[:27] + "...") if len(j.command) > 30 else j.command
        click.echo(f"{j.id:<15} {j.attempts:<10} {cmd_trunc:<30} {j.updated_at}")
    click.echo("-" * 80 + "\n")


@dlq_group.command(name="retry")
@click.argument("job_id", type=str)
def dlq_retry_cmd(job_id: str):
    """
    Retries a job from Dead Letter Queue by resetting state to 'pending'
    and attempts counter to 0.
    """
    job_service = JobService()
    try:
        job = job_service.retry_dlq_job(job_id)
        click.echo(f"Successfully retried DLQ job '{job.id}'. State reset to '{job.state}' with attempts=0.")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()
