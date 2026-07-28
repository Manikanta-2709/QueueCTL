"""
CLI command module for querying job lists.
Usage:
  queuectl list --state pending
  queuectl list --state pending --json
"""

import json
import click
from queuectl.services.job_service import JobService


@click.command(name="list")
@click.option("--state", type=str, default=None, help="Filter jobs by state (pending, processing, completed, failed, dead).")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output strictly formatted JSON.")
def list_cmd(state: str | None, json_mode: bool):
    """Lists jobs in queue with optional state filtering and JSON output."""
    job_service = JobService()
    jobs = job_service.list_jobs(state=state)

    if json_mode:
        # Output ONLY raw JSON array - nothing else
        job_dicts = [j.to_dict() for j in jobs]
        click.echo(json.dumps(job_dicts, indent=2))
        return

    if not jobs:
        state_str = f" with state '{state}'" if state else ""
        click.echo(f"No jobs found{state_str}.")
        return

    click.echo(f"\nFound {len(jobs)} job(s):")
    click.echo("-" * 80)
    click.echo(f"{'ID':<15} {'STATE':<12} {'ATTEMPTS':<10} {'COMMAND':<25} {'CREATED AT'}")
    click.echo("-" * 80)
    for j in jobs:
        cmd_trunc = (j.command[:22] + "...") if len(j.command) > 25 else j.command
        click.echo(f"{j.id:<15} {j.state:<12} {j.attempts:<10} {cmd_trunc:<25} {j.created_at}")
    click.echo("-" * 80 + "\n")
