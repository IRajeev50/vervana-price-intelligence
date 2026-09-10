"""Intelligence module (M9): horizons, chain rules, honesty gates, storage, web."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from vervana.intelligence import (
    Direction,
    SignalStatus,
    build_chain,
    build_report,
    forecast_horizon,
    format_report,
    load_profiles,
    save_record,
)
from vervana.intelligence.crops import get_profile
from vervana.intelligence.signals import (
    Signal,
    import_signals_csv,
    load_fixture_signals,
    merge_signals,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Offline web client: temp SQLite + registry seed (pattern from test_web.py)."""
    from fastapi.testclient import TestClient

    import vervana.models  # noqa: F401 - register tables
    from vervana.db.base import Base
    from vervana.db.engine import make_engine, session_scope
    from vervana.repository.registry import seed_registry

    db = tmp_path / "web.sqlite3"
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{db}")
    Base.metadata.create_all(make_engine(f"sqlite:///{db}"))
    seed_dir = Path(__file__).resolve().parent.parent / "data" / "seed"
    with session_scope() as s:
        seed_registry(s, seed_dir)
    from vervana.web.app import app

    return TestClient(app)


def _sig(kind, value, status=SignalStatus.observed, region="India"):
    return Signal(kind, region, date(2026, 9, 1), value, None, status, "test-source")


def test_sugar_horizon_is_months_not_weeks():
    h = forecast_horizon(get_profile("Sugarcane"))
    assert h.max_days >= 180  # 6+ months - the 6-8 month claim is biologically defensible
    assert "storage buffer" in h.basis


def test_perishable_horizon_is_weeks():
    h = forecast_horizon(get_profile("Tomato"))
    assert h.max_days <= 60
    assert "weeks" in h.label


def test_unknown_commodity_fails_closed_to_short_horizon():
    h = forecast_horizon(get_profile("Dragonfruit"))
    assert h.max_days <= 60
    assert "fail closed" in h.basis


def test_profiles_cover_seeded_basket():
    profiles = load_profiles()
    for name in ("Potato", "Onion", "Tomato", "Capsicum", "Cauliflower", "Green Chilli"):
        assert name in profiles


def test_chain_unknown_without_inputs():
    steps = build_chain([])
    assert all(s.direction == Direction.unknown for s in steps)
    assert all(s.confidence == 0.0 or s.name == "impacts" for s in steps)


def test_chain_detects_supply_deficit():
    signals = [
        _sig("rainfall_deficit_pct", -25),
        _sig("ndvi_anomaly", -0.08),
        _sig("reservoir_pct", 50),
        _sig("acreage_change_pct", -5),
        _sig("production_lmt", 279),
        _sig("consumption_lmt", 282),
        _sig("stocks_lmt", 35),
    ]
    steps = {s.name: s for s in build_chain(signals)}
    assert steps["production"].direction == Direction.down
    assert steps["balance"].direction == Direction.down
    assert steps["price_pressure"].direction == Direction.up
    assert steps["production"].status == "observed"


def test_simulated_input_caps_confidence():
    signals = [
        _sig("rainfall_deficit_pct", -25, status=SignalStatus.simulated),
        _sig("ndvi_anomaly", -0.08),
    ]
    steps = {s.name: s for s in build_chain(signals)}
    assert steps["production"].confidence <= 0.35
    assert steps["production"].status == "simulated"


def test_merge_observed_kind_drops_simulated_standins():
    observed = [_sig("stocks_lmt", 35, region="India")]
    simulated = [_sig("stocks_lmt", 99, status=SignalStatus.simulated, region="India")]
    merged = merge_signals(observed, simulated, required_kinds=["stocks_lmt", "ndvi_anomaly"])
    stocks = [s for s in merged if s.kind == "stocks_lmt"]
    assert len(stocks) == 1 and stocks[0].value_numeric == 35
    assert any(s.kind == "ndvi_anomaly" and s.status == SignalStatus.missing for s in merged)


def test_missing_kinds_get_markers():
    merged = merge_signals([], [], required_kinds=["reservoir_pct"])
    assert merged[0].status == SignalStatus.missing


def test_fixture_signals_are_all_labelled_simulated():
    fixture = load_fixture_signals()
    assert fixture, "sugar fixture must exist"
    assert all(s.status == SignalStatus.simulated for s in fixture)
    assert all("SIMULATED" in s.note for s in fixture)


def test_import_rejects_unsourced_or_unknown(session, tmp_path: Path):
    csv_path = tmp_path / "sig.csv"
    csv_path.write_text(
        "signal_type,region,on_date,value_numeric,value_text,source,source_url\n"
        "rainfall_deficit_pct,Maharashtra,2026-09-01,-12,,IMD,https://mausam.imd.gov.in\n"
        "rainfall_deficit_pct,Karnataka,2026-09-01,-23,,,\n"
        "bogus_kind,India,2026-09-01,1,,IMD,\n",
        encoding="utf-8",
    )
    res = import_signals_csv(session, csv_path)
    assert res["added"] == 1
    assert res["rejected"] == 2


def test_report_sugar_worked_example_is_watchlist(session):
    report = build_report(session, "Sugarcane")
    # Fixture-only inputs => the verdict must be the simulated watchlist, never "signal".
    assert "simulated" in report.verdict
    assert report.n_simulated > 0
    assert report.n_missing > 0  # e.g. crushing_recovery_pct, arrivals, input sales
    assert report.confidence <= 0.35
    text = format_report(report)
    assert "Not trading advice" in text
    assert "missing input" in text


def test_report_observed_only_excludes_fixture(session):
    report = build_report(session, "Sugarcane", include_simulated=False)
    assert report.n_simulated == 0
    assert report.verdict == "no signal"  # no observed feeds connected yet


def test_save_record_is_append_only(session):
    from vervana.models.intelligence import IntelligenceReportRecord

    report = build_report(session, "Sugarcane")
    id1 = save_record(session, report)
    id2 = save_record(session, report)
    assert id2 > id1
    rows = session.query(IntelligenceReportRecord).count()
    assert rows == 2


def test_web_pages(client):
    r = client.get("/intelligence")
    assert r.status_code == 200
    assert "Sugarcane" in r.text
    r = client.get("/intelligence/Sugarcane")
    assert r.status_code == 200
    assert "simulated" in r.text.lower()
    assert "Not trading advice" in r.text
    assert "DMI" in r.text  # page disclaimers still apply


def test_api_endpoint_requires_key(client):
    assert client.get("/api/v1/intelligence/Sugarcane").status_code == 401
    r = client.get("/api/v1/intelligence/Sugarcane", headers={"X-API-Key": "demo-key"})
    assert r.status_code == 200
    body = r.json()
    assert body["commodity"] == "Sugarcane"
    assert body["n_simulated"] > 0
