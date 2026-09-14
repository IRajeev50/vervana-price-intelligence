"""Admin supply endpoints (M11 follow-up): NDVI trigger + IMD rainfall CSV import.

Deployed free-tier hosts have no shell, so these HTTP endpoints are how the
operator runs the supply feeds server-side. Tests stub the network at the
connector boundary - nothing here touches CDSE or IMD.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import vervana.models  # noqa: F401
from vervana.connectors.imd import ImdRainfallConnector
from vervana.connectors.sentinel2 import Sentinel2NdviConnector
from vervana.db.base import Base
from vervana.db.engine import make_engine, session_scope
from vervana.models.context import ContextSignal

H = {"X-API-Key": "test-key"}

NDVI_RECORDS = [
    {
        "zone": "nashik-onion",
        "district": "Nashik",
        "state": "Maharashtra",
        "on_date": "2026-09-13",
        "current_mean": 0.62,
        "baseline_mean": 0.55,
    }
]

RAINFALL_CSV = (
    "district,state,date,dep_pct\n"
    "Nashik,Maharashtra,2026-09-13,45\n"
    ",,,\n"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "supply_admin.sqlite3"
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("VERVANA_PUBLIC_API_KEYS", "test-key")
    monkeypatch.setenv("VERVANA_PUBLIC_API_RATE_PER_MIN", "30")
    Base.metadata.create_all(make_engine(f"sqlite:///{db}"))
    from vervana.web import api as api_mod

    api_mod._hits.clear()  # rate-limiter state is process-global; reset per test
    from vervana.web.app import app

    return TestClient(app)


def _signals(kind):
    with session_scope() as s:
        return (
            s.execute(select(ContextSignal).where(ContextSignal.signal_type == kind))
            .scalars()
            .all()
        )


def test_ndvi_requires_key(client):
    assert client.post("/api/v1/admin/supply/ndvi").status_code == 401


def test_ndvi_unknown_zone_404(client, monkeypatch):
    monkeypatch.setattr(
        Sentinel2NdviConnector, "enabled", lambda self, settings=None: True
    )
    r = client.post("/api/v1/admin/supply/ndvi?zone=bogus-zone", headers=H)
    assert r.status_code == 404


def test_ndvi_409_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(
        Sentinel2NdviConnector, "enabled", lambda self, settings=None: False
    )
    r = client.post("/api/v1/admin/supply/ndvi", headers=H)
    assert r.status_code == 409
    assert "VERVANA_CDS_CLIENT_ID" in r.json()["detail"]


def test_ndvi_endpoint_ingests_signals(client, monkeypatch):
    monkeypatch.setattr(
        Sentinel2NdviConnector, "enabled", lambda self, settings=None: True
    )
    monkeypatch.setattr(
        Sentinel2NdviConnector, "fetch_raw", lambda self, **_: NDVI_RECORDS
    )
    r = client.post("/api/v1/admin/supply/ndvi", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["rows_in"] == 1
    assert body["accepted"] == 1
    assert body["rejected"] == 0
    rows = _signals("ndvi_anomaly")
    assert len(rows) == 1
    assert rows[0].region == "Nashik"
    assert rows[0].on_date.isoformat() == "2026-09-13"
    assert abs(rows[0].value_numeric - 0.07) < 1e-6  # 0.62 - 0.55


def test_rainfall_requires_key(client):
    assert client.post("/api/v1/admin/supply/rainfall").status_code == 401


def test_rainfall_endpoint_imports_csv_body(client):
    r = client.post(
        "/api/v1/admin/supply/rainfall",
        headers={**H, "Content-Type": "text/csv"},
        content=RAINFALL_CSV,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["rows_in"] == 2
    assert body["accepted"] == 1
    assert body["rejected"] == 1  # blank row: missing district/date
    rows = _signals("rainfall_deficit_pct")
    assert len(rows) == 1
    assert rows[0].region == "Nashik"
    assert rows[0].value_numeric == 45
    assert rows[0].source == "IMD district rainfall"


def test_rainfall_empty_body_without_fetch_url_409(client, monkeypatch):
    def _no_url(self, **kwargs):
        raise NotImplementedError("no VERVANA_IMD_DISTRICT_RAINFALL_URL set")

    monkeypatch.setattr(ImdRainfallConnector, "fetch_raw", _no_url)
    r = client.post("/api/v1/admin/supply/rainfall", headers=H, content="")
    assert r.status_code == 409
