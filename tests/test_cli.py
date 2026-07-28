"""
Integration tests for queuectl CLI commands using Click CliRunner.
"""

import json
import pytest
from click.testing import CliRunner
from queuectl.cli.main import cli


def test_cli_enqueue_and_status(tmp_path, monkeypatch):
    db_file = tmp_path / "cli_test.db"
    monkeypatch.setenv("QUEUECTL_DB_PATH", str(db_file))

    runner = CliRunner()

    # Enqueue job
    result = runner.invoke(cli, ["enqueue", '{"id":"c1","command":"echo hello_cli"}'])
    assert result.exit_code == 0
    assert "Job 'c1' enqueued successfully" in result.output

    # Check status
    res_status = runner.invoke(cli, ["status"])
    assert res_status.exit_code == 0
    assert "Pending    : 1" in res_status.output


def test_cli_list_json_output(tmp_path, monkeypatch):
    db_file = tmp_path / "cli_json.db"
    monkeypatch.setenv("QUEUECTL_DB_PATH", str(db_file))

    runner = CliRunner()

    runner.invoke(cli, ["enqueue", '{"id":"j_json","command":"echo json"}'])

    res_list = runner.invoke(cli, ["list", "--state", "pending", "--json"])
    assert res_list.exit_code == 0
    
    parsed = json.loads(res_list.output.strip())
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "j_json"


def test_cli_config_set_get(tmp_path, monkeypatch):
    db_file = tmp_path / "cli_config.db"
    monkeypatch.setenv("QUEUECTL_DB_PATH", str(db_file))

    runner = CliRunner()

    res_set = runner.invoke(cli, ["config", "set", "max-retries", "5"])
    assert res_set.exit_code == 0
    assert "max-retries = 5" in res_set.output

    res_get = runner.invoke(cli, ["config", "get", "max-retries"])
    assert res_get.exit_code == 0
    assert "max-retries = 5" in res_get.output
