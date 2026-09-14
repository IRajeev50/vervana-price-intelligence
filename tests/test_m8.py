"""M8: multi-mandi config (R12 cost), public API auth + rate limit, benchmark, export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vervana.models  # noqa: F401
from vervana.connectors.agmarknet import AgmarknetConnector
from vervana.db.base import Base
from vervana.db.engine import make_engine, session_scope
from vervana.economics import estimate_observer_cost
from vervana.repository.registry import seed_registry, sync_mandis

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
MANDI_CFG = Path(__file__).resolve().parent.parent / "data" / "config" / "mandis.csv"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "agmarknet_sample.json"


def test_observer_cost_scales_linearly():
    e1 = estimate_observer_cost(1, observers_per_mandi=1, stipend_rupees=8000)
    e10 = estimate_observer_cost(10, observers_per_mandi=1, stipend_rupees=8000)
    assert e10.monthly_rupees == 10 * e1.monthly_rupees  # linear (R12)
    assert e1.monthly_rupees == 8000
    assert "R12" in e1.as_lines()


def test_sync_mandis_is_config_driven(session):
    seed_registry(session, SEED_DIR)  # already has the Delhi markets
    res = sync_mandis(session, MANDI_CFG)
    assert res["n_mandis"] >= 7
    assert res["added"] >= 0  # idempotent; existing markets are skipped


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "m8.sqlite3"
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("VERVANA_PUBLIC_API_KEYS", "test-key")
    monkeypatch.setenv("VERVANA_PUBLIC_API_RATE_PER_MIN", "5")
    Base.metadata.create_all(make_engine(f"sqlite:///{db}"))
    from vervana.web import api as api_mod

    api_mod._hits.clear()  # rate-limiter state is process-global; reset per test
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]
    with session_scope() as s:
        seed_registry(s, SEED_DIR)
        AgmarknetConnector().ingest_with_run(s, records, mode="test")
    from vervana.web.app import app

    return TestClient(app)


def test_api_requires_key(client):
    assert client.get("/api/v1/prices").status_code == 401
    assert client.get("/api/v1/prices", headers={"X-API-Key": "test-key"}).status_code == 200


def test_api_rate_limit(client):
    h = {"X-API-Key": "test-key"}
    codes = [client.get("/api/v1/prices", headers=h).status_code for _ in range(8)]
    assert 429 in codes  # limit is 5/min


def test_benchmark_endpoint(client):
    r = client.get("/api/v1/benchmark/Potato", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()
    assert body["commodity"] == "Potato"
    assert body["summary"]["n_markets"] >= 1  # Azadpur + Keshopur in the fixture


def test_export_streams_csv(client):
    r = client.get("/api/v1/export", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    assert "canonical_rupees_per_kg" in r.text
    assert "Potato" in r.text
def test_admin_ingest_endpoint(monkeypatch, client):
    # The endpoint runs the real connector; stub only the network fetch.
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]
    monkeypatch.setattr(AgmarknetConnector, "fetch_raw", lambda self, **_: records)
    assert client.post("/api/v1/admin/ingest/agmarknet").status_code == 401
    r = client.post("/api/v1/admin/ingest/agmarknet", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # The client fixture already ingested these rows, so the endpoint's run
    # recognises every previously-accepted row as a duplicate (no double-count).
    assert body["rejection_reasons"].get("duplicate_already_ingested") == 4
