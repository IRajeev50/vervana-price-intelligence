"""First-run setup checklist: shared collector, CLI setup/doctor, web empty states.

All offline: temp SQLite, no network. The checklist must never invent live data -
it reports seed (reference) data and live observations as the separate things
they are.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import vervana.models  # noqa: F401 - register tables
from vervana.cli import app as cli_app
from vervana.config import Settings
from vervana.connectors.agmarknet import AgmarknetConnector
from vervana.db.base import Base
from vervana.db.engine import make_engine, session_scope
from vervana.models.ingest import IngestRun
from vervana.repository.registry import seed_registry
from vervana.setup_status import collect_setup_steps
from vervana.time import now_utc

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "agmarknet_sample.json"


def _fresh_db(tmp_path, monkeypatch) -> str:
    url = f"sqlite:///{tmp_path / 'setup.sqlite3'}"
    monkeypatch.setenv("VERVANA_DATABASE_URL", url)
    Base.metadata.create_all(make_engine(url))
    return url


def _by_key(steps):
    return {s.key: s for s in steps}


def test_empty_db_nothing_done(session):
    steps = _by_key(collect_setup_steps(session, Settings()))
    assert not steps["registry"].ok
    assert not steps["api_key"].ok
    assert not steps["live_data"].ok
    # Each open step names the exact next action; no secrets are echoed.
    assert steps["registry"].action == "uv run vervana setup"
    assert "VERVANA_DATA_GOV_IN_API_KEY" in steps["api_key"].action
    assert steps["live_data"].action.startswith("uv run vervana ingest agmarknet")


def test_seeded_registry_marks_reference_data_done(session, monkeypatch):
    seed_registry(session, SEED_DIR)
    monkeypatch.setenv("VERVANA_DATA_GOV_IN_API_KEY", "test-key-not-real")
    steps = _by_key(collect_setup_steps(session, Settings()))
    assert steps["registry"].ok
    assert steps["api_key"].ok
    # Seed data is reference data only: it must NOT satisfy the live-data step.
    assert not steps["live_data"].ok
    assert "no live prices yet" in steps["live_data"].detail


def test_failed_run_is_surfaced_not_hidden(session, monkeypatch):
    seed_registry(session, SEED_DIR)
    monkeypatch.setenv("VERVANA_DATA_GOV_IN_API_KEY", "test-key-not-real")
    session.add(
        IngestRun(
            connector="agmarknet",
            mode="daily",
            status="failed",
            started_at=now_utc(),
            error="httpx.ReadTimeout",
        )
    )
    session.flush()
    steps = _by_key(collect_setup_steps(session, Settings()))
    assert not steps["live_data"].ok
    assert "failed" in steps["live_data"].detail
    assert steps["live_data"].action.startswith("uv run vervana ingest agmarknet")


def test_ingested_observations_complete_the_checklist(session, monkeypatch):
    seed_registry(session, SEED_DIR)
    monkeypatch.setenv("VERVANA_DATA_GOV_IN_API_KEY", "test-key-not-real")
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]
    AgmarknetConnector().ingest_with_run(session, records, mode="test")
    session.flush()
    steps = _by_key(collect_setup_steps(session, Settings()))
    assert all(s.ok for s in steps.values())
    assert steps["live_data"].action is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_setup_is_idempotent_and_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{tmp_path / 'cli.sqlite3'}")
    runner = CliRunner()
    first = runner.invoke(cli_app, ["setup"])
    assert first.exit_code == 0, first.output
    assert "commodities" in first.output
    # Without a key and without a capture, the checklist must say so honestly.
    assert "no key found" in first.output
    assert "no live prices yet" in first.output
    # Registry rows exist after one run ...
    with session_scope() as s:
        steps = _by_key(collect_setup_steps(s, Settings()))
    assert steps["registry"].ok
    # ... and a second run neither duplicates nor fails.
    second = runner.invoke(cli_app, ["setup"])
    assert second.exit_code == 0, second.output
    with session_scope() as s:
        steps2 = _by_key(collect_setup_steps(s, Settings()))
    assert steps2["registry"].ok


def test_cli_doctor_exit_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{tmp_path / 'doc.sqlite3'}")
    runner = CliRunner()
    # Unmigrated database: doctor fails loudly and points at `vervana setup`.
    missing = runner.invoke(cli_app, ["doctor"])
    assert missing.exit_code == 1
    assert "uv run vervana setup" in missing.output

    runner.invoke(cli_app, ["setup"])
    open_steps = runner.invoke(cli_app, ["doctor"])
    assert open_steps.exit_code == 1  # key + live data still missing

    monkeypatch.setenv("VERVANA_DATA_GOV_IN_API_KEY", "test-key-not-real")
    with session_scope() as s:
        records = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]
        AgmarknetConnector().ingest_with_run(s, records, mode="test")
    done = runner.invoke(cli_app, ["doctor"])
    assert done.exit_code == 0, done.output


# ---------------------------------------------------------------------------
# Web empty states
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_client(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    from vervana.web.app import app

    return TestClient(app)


def test_dashboard_shows_setup_checklist_when_empty(empty_client):
    r = empty_client.get("/")
    assert r.status_code == 200
    assert "First-run setup" in r.text
    assert "uv run vervana setup" in r.text
    assert "VERVANA_DATA_GOV_IN_API_KEY" in r.text


def test_prices_empty_state_is_actionable_when_no_data(empty_client):
    r = empty_client.get("/prices")
    assert r.status_code == 200
    assert "No live prices yet" in r.text
    assert "uv run vervana setup" in r.text


def test_dashboard_hides_checklist_once_ready(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    monkeypatch.setenv("VERVANA_DATA_GOV_IN_API_KEY", "test-key-not-real")
    with session_scope() as s:
        seed_registry(s, SEED_DIR)
        records = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]
        AgmarknetConnector().ingest_with_run(s, records, mode="test")
    from vervana.web.app import app

    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "First-run setup" not in r.text
