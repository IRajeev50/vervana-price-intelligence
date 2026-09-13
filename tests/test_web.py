"""Web serving layer smoke tests (offline: temp SQLite + fixture, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vervana.models  # noqa: F401 - register tables
from vervana.connectors.agmarknet import AgmarknetConnector
from vervana.db.base import Base
from vervana.db.engine import make_engine, session_scope
from vervana.repository.registry import seed_registry

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "agmarknet_sample.json"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "web.sqlite3"
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{db}")
    Base.metadata.create_all(make_engine(f"sqlite:///{db}"))
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]
    with session_scope() as s:
        seed_registry(s, SEED_DIR)
        AgmarknetConnector().ingest_with_run(s, records, mode="test")
    from vervana.web.app import app

    return TestClient(app)


def test_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Vervana" in r.text
    # Mandatory disclaimers on every page (Part 7).
    assert "DMI" in r.text
    assert "GODL-India" in r.text


def test_prices_has_rows_and_evidence_links(client):
    r = client.get("/prices")
    assert r.status_code == 200
    assert "Potato" in r.text
    assert "/evidence/" in r.text


def test_evidence_shows_provenance(client):
    r = client.get("/evidence/1")
    assert r.status_code == 200
    assert "api.data.gov.in" in r.text  # the real source URL
    assert "Raw source record" in r.text


def test_coverage_page(client):
    r = client.get("/coverage")
    assert r.status_code == 200
    assert "R5" in r.text


def test_api_observation_traces(client):
    r = client.get("/api/observations/1")
    assert r.status_code == 200
    body = r.json()
    assert body["source_url"].startswith("https://api.data.gov.in/")
    assert body["unit_raw"] == "Quintal"


def test_review_and_ingest_pages(client):
    assert client.get("/review").status_code == 200
    assert client.get("/ingest").status_code == 200



def test_digest_is_structured_and_keeps_provenance(client):
    r = client.get("/digest")
    assert r.status_code == 200
    assert "Market spread board" in r.text
    assert "Wholesale reference" in r.text
    assert "Retail market" in r.text
    assert "Evidence quality" in r.text
    assert "/evidence/" in r.text
    assert "View plain-text broadcast payload" in r.text
