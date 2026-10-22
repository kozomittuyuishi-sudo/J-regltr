import pytest
from typer.testing import CliRunner

from jreg.cli import main as cli
from jreg.core.config import settings


runner = CliRunner()


def test_init(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "config_dir", str(tmp_path / "config"))
    initialized = []
    monkeypatch.setattr(cli, "init_db", lambda: initialized.append(True))
    result = runner.invoke(cli.app, ["init"])
    assert result.exit_code == 0, result.output
    assert "Configuration directory ready" in result.output
    assert "Database initialized" in result.output
    assert initialized == [True]


def test_status(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "app_name", "J Regulator")
    monkeypatch.setattr(settings, "config_dir", str(tmp_path))
    monkeypatch.setattr(settings, "database_url", "sqlite:///./missing.db")
    result = runner.invoke(cli.app, ["status"])
    assert result.exit_code == 0
    assert "J Regulator Status" in result.output
    assert "Not initialized" in result.output


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["providers", "list"], "anthropic"),
        (["models", "list"], "gpt-4"),
        (["providers-list"], "openai"),
        (["models-list"], "claude-3"),
        (["routing", "show"], "max retries per model: 1"),
    ],
)
def test_registered_list_and_routing_commands(arguments, expected):
    result = runner.invoke(cli.app, arguments)
    assert result.exit_code == 0, result.output
    assert expected in result.output


@pytest.mark.parametrize(
    ("failure", "expected_model", "expected_error"),
    [
        ("success", "gpt-4", None),
        ("quota_exhausted", "claude-3", "QUOTA_EXHAUSTED"),
        ("rate_limit", "claude-3", "RATE_LIMIT"),
        ("timeout", "claude-3", "TIMEOUT"),
        ("error", "claude-3", "UNKNOWN"),
    ],
)
def test_deterministic_mock_simulation(failure, expected_model, expected_error):
    result = runner.invoke(cli.app, ["models", "simulate", "--failure", failure])
    assert result.exit_code == 0, result.output
    assert f"Selected model: {expected_model}" in result.output
    if expected_error:
        assert expected_error in result.output


def test_simulation_rejects_unsupported_failure_mode():
    result = runner.invoke(cli.app, ["models", "simulate", "--failure", "random"])
    assert result.exit_code != 0
    assert "Choose one of" in result.output


def test_help_lists_documented_command_groups():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for command in ("init", "status", "providers", "models", "routing"):
        assert command in result.output
