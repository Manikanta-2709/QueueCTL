"""
CLI command module for system configuration settings.
Usage:
  queuectl config set max-retries 3
  queuectl config set backoff-base 2
  queuectl config get max-retries
"""

import click
from queuectl.services.config_service import ConfigService


@click.group(name="config")
def config_group():
    """Configuration management commands."""
    pass


@config_group.command(name="set")
@click.argument("key", type=str)
@click.argument("value", type=str)
def config_set_cmd(key: str, value: str):
    """Sets a system configuration setting key-value pair."""
    config_service = ConfigService()
    config_service.set_config(key, value)
    click.echo(f"Configuration updated: {key} = {value}")


@config_group.command(name="get")
@click.argument("key", type=str)
def config_get_cmd(key: str):
    """Gets current configuration setting value."""
    config_service = ConfigService()
    val = config_service.get_config(key, default="<not set>")
    click.echo(f"{key} = {val}")
