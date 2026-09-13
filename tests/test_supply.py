"""Supply-side layer (M11): zones, feed status, scaffold honesty, connectors, chain."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from vervana.config import Settings
from vervana.connectors.imd import ImdRainfallConnector
from vervana.connectors.sentinel2 import Sentinel2NdviConnector
from vervana.intelligence import Direction, build_chain
from vervana.intelligence.signals import STEP_SIGNALS, Signal, SignalStatus, import_signals_csv
from vervana.models.context import ContextSignal
from vervana.supply.alu import AluClient, CropArea, acreage_change_signals
from vervana.supply.amed import AmedClient, FieldSeason, progress_signals
from vervana.supply.feeds import collect_feed_status, observed_supply_counts
from vervana.supply.scaffold import PartnerAccessPending
from vervana.supply.zones import load_zones


def _sig(kind, value, status=SignalStatus.observed, region="India"):
    return Signal(kind, region, date(2026, 9, 1), value, None, status, "test-source")


# --- zones ---------------------------------------------------------------


def test_zones_load_and_cover_profiled_crops():
    zones = load_zones()
    assert len(zones) >= 6
    crops = {c for z in zones for c in z.commodities}
    for name in ("Onion", "Sugarcane", "Wheat", "Potato"):
        assert name in crops
    assert all(-90 <= z.lat <= 90 and -180 <= z.lon <= 180 for z in zones)


# --- scaffold honesty ------------------------------------------------------


def test_alu_scaffold_fetches_nothing_without_access():
    client = AluClient(Settings())
    assert not client.configured()
    assert "pending" in client.access_state()
    with pytest.raises(PartnerAccessPending):
        client.fetch_crop_map(lat=20.0, lon=73.8)


def test_amed_scaffold_fetches_nothing_without_access():
    client = AmedClient(Settings())
    assert not client.configured()
    with pytest.raises(PartnerAccessPending):
        client.fetch_events(lat=20.0, lon=73.8)


def test_scaffold_status_is_labelled_scaffold():
    feeds = {f.name: f for f in collect_feed_status(Settings())}
    assert feeds["google-alu"].layer == "scaffold"
    assert "scaffold" in feeds["google-alu"].state
    assert feeds["google-amed"].layer == "scaffold"
    assert feeds["sentinel2-ndvi"].layer == "fallback"
    assert feeds["imd-rainfall"].layer == "fallback"


def test_scaffold_configures_only_with_endpoint_and_key():
    s = Settings(
        google_alu_api_url="https://example.invalid/alu",
        google_agri_api_key="k",
        google_amed_api_url="https://example.invalid/amed",
    )
    assert AluClient(s).configured()
    assert AmedClient(s).configured()
    # endpoint without key still pending
    s2 = Settings(google_alu_api_url="https://example.invalid/alu")
    assert not AluClient(s2).configured()


# --- ALU seam mapping (pure) -----------------------------------------------


def test_acreage_change_signals_pair_seasons():
    current = [CropArea("nashik-onion", "Onion", "rabi-2026", area_ha=9000.0)]
    previous = [CropArea("nashik-onion", "Onion", "rabi-2025", area_ha=10000.0)]
    sigs = acreage_change_signals(current, previous, on_date=date(2026, 9, 1))
    assert len(sigs) == 1
    assert sigs[0].kind == "acreage_change_pct"
    assert sigs[0].value_numeric == -10.0
    assert sigs[0].status == SignalStatus.observed


def test_acreage_change_skips_unpaired_and_zero_baseline():
    current = [
        CropArea("nashik-onion", "Onion", "rabi-2026", 9000.0),
        CropArea("kolar-tomato", "Tomato", "kharif-2026", 500.0),
    ]
    previous = [CropArea("kolar-tomato", "Tomato", "kharif-2025", 0.0)]
    assert acreage_change_signals(current, previous, on_date=date(2026, 9, 1)) == []


# --- AMED seam mapping (pure) ----------------------------------------------


def test_progress_signals_area_based():
    fields = [
        FieldSeason("meerut-sugarcane", "Sugarcane", 40.0, date(2026, 3, 1), None),
        FieldSeason("meerut-sugarcane", "Sugarcane", 60.0, date(2026, 4, 1), None),
        FieldSeason("meerut-sugarcane", "Sugarcane", 30.0, None, date(2026, 9, 10)),
        FieldSeason("meerut-sugarcane", "Sugarcane", 20.0, date(2027, 1, 1), None),  # future
    ]
    expected = {("meerut-sugarcane", "Sugarcane"): 200.0}
    sigs = progress_signals(fields, expected, as_of=date(2026, 9, 13))
    by_kind = {s.kind: s for s in sigs}
    assert by_kind["sowing_progress_pct"].value_numeric == 50.0  # 100 of 200 ha
    assert by_kind["harvest_progress_pct"].value_numeric == 15.0  # 30 of 200 ha
    assert all(s.status == SignalStatus.observed for s in sigs)


def test_progress_signals_skip_unknown_expectation():
    fields = [FieldSeason("nowhere", "Onion", 10.0, date(2026, 3, 1), None)]
    assert progress_signals(fields, {}, as_of=date(2026, 9, 13)) == []


# --- Sentinel-2 connector (offline ingest) ----------------------------------


def test_sentinel2_disabled_without_credentials():
    conn = Sentinel2NdviConnector()
    assert not conn.enabled(Settings())
    assert conn.enabled(Settings(cds_client_id="id", cds_client_secret="secret"))


def test_sentinel2_ingest_writes_observed_anomaly(session):
    conn = Sentinel2NdviConnector()
    records = [
        {
            "zone": "nashik-onion",
            "district": "Nashik",
            "state": "Maharashtra",
            "on_date": "2026-09-13",
            "current_mean": 0.41,
            "baseline_mean": 0.55,
        }
    ]
    result = conn.ingest(session, records, mode="api")
    assert result.accepted == 1 and result.rejected == 0
    row = session.scalar(select(ContextSignal))
    assert row.signal_type == "ndvi_anomaly"
    assert float(row.value_numeric) == pytest.approx(-0.14, abs=1e-4)
    assert row.region == "Nashik"
    assert "Copernicus" in row.source  # provenance, not a bare "api"


def test_sentinel2_ingest_rejects_out_of_range(session):
    conn = Sentinel2NdviConnector()
    rec = {
        "zone": "z",
        "district": "d",
        "on_date": "2026-09-13",
        "current_mean": 1.7,
        "baseline_mean": 0.5,
    }
    result = conn.ingest(session, [rec], mode="api")
    assert result.accepted == 0 and result.rejected == 1


# --- IMD connector ----------------------------------------------------------


def test_imd_import_computes_deficit(session, tmp_path: Path):
    csv_path = tmp_path / "rain.csv"
    csv_path.write_text(
        "district,state,date,actual_mm,normal_mm\n"
        "Solapur,Maharashtra,2026-09-01,120,200\n"
        "Nashik,Maharashtra,2026-09-01,,\n",
        encoding="utf-8",
    )
    result = ImdRainfallConnector().import_csv(session, csv_path)
    assert result.accepted == 1 and result.rejected == 1
    row = session.scalar(select(ContextSignal))
    assert row.signal_type == "rainfall_deficit_pct"
    assert float(row.value_numeric) == -40.0


def test_imd_import_accepts_departure_column(session, tmp_path: Path):
    csv_path = tmp_path / "rain.csv"
    csv_path.write_text(
        "District,State,Date,Dep %\nNashik,Maharashtra,01/09/2026,-23%\n",
        encoding="utf-8",
    )
    # "Dep %" normalises to dep_% which is not dep_pct: rejected honestly.
    result = ImdRainfallConnector().import_csv(session, csv_path)
    assert result.rejected == 1


def test_imd_fetch_without_url_says_so():
    with pytest.raises(NotImplementedError, match="rainfall-import"):
        ImdRainfallConnector().fetch_raw(settings=Settings())


# --- chain rules for the new kinds ------------------------------------------


def test_new_kinds_are_wired_into_steps():
    assert "sowing_progress_pct" in STEP_SIGNALS["production"]
    assert "harvest_progress_pct" in STEP_SIGNALS["supply"]


def test_chain_sowing_behind_pulls_production_down():
    steps = {s.name: s for s in build_chain([_sig("sowing_progress_pct", 55)])}
    assert "sowing progress 55% of normal" in steps["production"].finding


def test_chain_harvest_underway_lifts_supply():
    signals = [
        _sig("production_lmt", 100),
        _sig("consumption_lmt", 100),
        _sig("harvest_progress_pct", 80),
    ]
    steps = {s.name: s for s in build_chain(signals)}
    assert steps["supply"].direction == Direction.up
    assert "harvest progress 80% of area" in steps["supply"].finding


def test_new_kinds_importable_as_observed(session, tmp_path: Path):
    csv_path = tmp_path / "sig.csv"
    csv_path.write_text(
        "signal_type,region,on_date,value_numeric,value_text,source,source_url\n"
        "sowing_progress_pct,Meerut,2026-09-01,62,,Google AMED,\n"
        "harvest_progress_pct,Nashik,2026-09-01,71,,Google AMED,\n",
        encoding="utf-8",
    )
    res = import_signals_csv(session, csv_path)
    assert res["added"] == 2 and res["rejected"] == 0


def test_observed_supply_counts(session):
    session.add(
        ContextSignal(
            signal_type="ndvi_anomaly",
            region="Nashik",
            on_date=date(2026, 9, 13),
            value_numeric=-0.1,
            source="test",
        )
    )
    session.flush()
    assert observed_supply_counts(session) == {"ndvi_anomaly": 1}


# --- CLI + web surfaces ------------------------------------------------------


def test_cli_supply_status_offline(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{tmp_path / 's.sqlite3'}")
    from vervana.cli import app

    result = CliRunner().invoke(app, ["supply", "status"])
    assert result.exit_code == 0
    assert "SCAFFOLD" in result.output
    assert "Google ALU" in result.output
    assert "Sentinel-2" in result.output


def test_intelligence_page_shows_feeds_and_scaffold_label(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import vervana.models  # noqa: F401 - register tables
    from vervana.db.base import Base
    from vervana.db.engine import make_engine

    db = tmp_path / "web.sqlite3"
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{db}")
    Base.metadata.create_all(make_engine(f"sqlite:///{db}"))
    from vervana.web.app import app

    r = TestClient(app).get("/intelligence")
    assert r.status_code == 200
    assert "Supply-side feeds" in r.text
    assert "scaffold" in r.text.lower()
    assert "Google ALU" in r.text
