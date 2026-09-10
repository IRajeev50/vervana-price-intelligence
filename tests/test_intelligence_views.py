"""Intelligence web surfaces (M10): portfolio, outlook calendar, saved records.

Offline: temp SQLite + registry seed. Asserts the honesty contract end-to-end:
observed/simulated/missing labels survive the UI, past dates serve only saved
records (no lookahead), and empty states say so instead of implying data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vervana.models  # noqa: F401 - register tables
from vervana.db.base import Base
from vervana.db.engine import make_engine, session_scope
from vervana.repository.registry import seed_registry
from vervana.time import now_utc, to_ist

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "web.sqlite3"
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{db}")
    Base.metadata.create_all(make_engine(f"sqlite:///{db}"))
    with session_scope() as s:
        seed_registry(s, SEED_DIR)
    from vervana.web.app import app

    return TestClient(app)


def _save(client, commodity="Sugarcane"):
    r = client.post(f"/intelligence/{commodity}/save", follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"]


def test_portfolio_lists_crops_with_honesty_labels(client):
    r = client.get("/intelligence")
    assert r.status_code == 200
    assert "crop portfolio" in r.text
    assert "Sugarcane" in r.text and "Wheat" in r.text
    # Crops with no saved analysis must say so, not imply coverage.
    assert "no saved analysis" in r.text
    assert "Honest horizon" in r.text


def test_portfolio_after_save_shows_status_and_alerts(client):
    _save(client)
    r = client.get("/intelligence")
    assert "watchlist (simulated inputs)" in r.text
    assert "simulated inputs cap confidence" in r.text
    assert "missing input(s)" in r.text
    assert "As of" in r.text  # as-of timestamp on the summary
    assert "/intelligence/record/" in r.text


def test_save_then_record_roundtrip_preserves_provenance(client):
    loc = _save(client)
    r = client.get(loc)
    assert r.status_code == 200
    assert "Historical snapshot" in r.text
    assert "stored unedited" in r.text
    assert "no lookahead" in r.text
    # honesty labels survive the stored round-trip
    assert "simulated" in r.text and "missing" in r.text
    assert "watchlist (simulated inputs)" in r.text


def test_record_404_for_unknown_id(client):
    assert client.get("/intelligence/record/999").status_code == 404


def test_record_json_api_traces(client):
    loc = _save(client)
    rec_id = loc.rsplit("/", 1)[-1]
    r = client.get(f"/api/intelligence/records/{rec_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["commodity"] == "Sugarcane"
    assert body["report"]["horizon"]["label"]
    assert body["n_simulated"] >= 1
    assert client.get("/api/intelligence/records/999").json() == {"error": "not found"}


def test_calendar_month_and_empty_day_state(client):
    _save(client)
    # The app groups outlooks by IST date (Asia/Kolkata policy); the test must too,
    # or it queries the wrong day in the hours where UTC and IST dates differ.
    today = to_ist(now_utc()).date()
    r = client.get(f"/intelligence/history?month={today:%Y-%m}")
    assert r.status_code == 200
    assert "Outlook calendar" in r.text
    assert "saved outlook" in r.text
    # today holds the saved record -> day view lists it
    r2 = client.get(f"/intelligence/history/{today.isoformat()}")
    assert r2.status_code == 200
    assert "view saved outlook" in r2.text
    # a day with nothing recorded says exactly that (no fabricated history)
    r3 = client.get("/intelligence/history/2020-01-15")
    assert "No outlooks were saved" in r3.text
    assert "never reconstructs" in r3.text


def test_calendar_bad_date_404(client):
    assert client.get("/intelligence/history/not-a-date").status_code == 404


def test_region_filter_scopes_signal_table_only(client):
    r = client.get("/intelligence/Sugarcane?region=Solapur")
    assert r.status_code == 200
    assert "Solapur" in r.text
    assert "this filter narrows the input table only" in r.text
    # an unknown region yields an honest empty state, not invented signals
    r2 = client.get("/intelligence/Sugarcane?region=Nowhere")
    assert "No signals recorded for Nowhere" in r2.text


def test_live_detail_offers_save_and_keeps_labels(client):
    r = client.get("/intelligence/Sugarcane")
    assert r.status_code == 200
    assert "Save this outlook to the audit log" in r.text
    assert "simulated" in r.text
    assert "current outlook" in r.text
