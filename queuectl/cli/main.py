"""
Main CLI entrypoint for queuectl application.
Assembles all Click command groups and subcommands.
"""

import click
from queuectl.cli.enqueue import enqueue_cmd
from queuectl.cli.worker import worker_group
from queuectl.cli.status import status_cmd
from queuectl.cli.list import list_cmd
from queuectl.cli.dlq import dlq_group
from queuectl.cli.config import config_group


@click.group()
def cli():
    """queuectl - Production-grade local job queue CLI engine."""
    pass


# Register top-level commands matching requirement specification
cli.add_command(enqueue_cmd)
cli.add_command(worker_group)
cli.add_command(status_cmd)
cli.add_command(list_cmd)
cli.add_command(dlq_group)
cli.add_command(config_group)


def main():
    cli()


if __name__ == "__main__":
    main()
