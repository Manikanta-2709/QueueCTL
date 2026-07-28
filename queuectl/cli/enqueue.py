"""
CLI command module for enqueuing jobs into queuectl.
Usage: queuectl enqueue '{"id":"job1","command":"echo hello"}'
"""

import json
import click
from queuectl.services.job_service import JobService
from queuectl.utils.logger import get_logger

logger = get_logger("queuectl.cli.enqueue")


@click.command(name="enqueue")
@click.argument("payload", type=str)
def enqueue_cmd(payload: str):
    """
    Enqueues a new job into the system queue.
    Expects a JSON payload string containing 'id' and 'command' keys.
    Example: queuectl enqueue '{"id":"job1","command":"echo hello"}'
    """
    try:
        data = json.loads(payload)
        job_id = data.get("id")
        command = data.get("command")
        max_retries = data.get("max_retries")

        if not job_id:
            click.echo("Error: JSON payload must contain an 'id' field.", err=True)
            raise click.Abort()
        if not command:
            click.echo("Error: JSON payload must contain a 'command' field.", err=True)
            raise click.Abort()

        job_service = JobService()
        job = job_service.enqueue_job(job_id=job_id, command=command, max_retries=max_retries)
        click.echo(f"Job '{job.id}' enqueued successfully (state: {job.state}).")

    except json.JSONDecodeError:
        click.echo("Error: Invalid JSON payload provided to enqueue command.", err=True)
        raise click.Abort()
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()
