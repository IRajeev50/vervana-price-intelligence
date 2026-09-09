"""Smoke test: package imports and the CLI healthcheck exits 0."""

from __future__ import annotations

from typer.testing import CliRunner

import vervana
from vervana.cli import app

runner = CliRunner()


def test_package_imports() -> None:
    assert vervana.__version__


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert vervana.__version__ in result.stdout


def test_healthcheck_command() -> None:
    result = runner.invoke(app, ["healthcheck"])
    assert result.exit_code == 0
    assert "ok" in result.stdout
