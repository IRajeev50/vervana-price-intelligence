"""Agmarknet connector: field mapping, validation, canonical conversion, ingest_run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.connectors.agmarknet import (
    AgmarknetConnector,
    SchemaError,
    map_fields,
)
from vervana.models.ingest import IngestRun
from vervana.models.observations import PriceObservation
from vervana.repository.registry import seed_registry

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "agmarknet_sample.json"
SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def _records() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]


def test_map_fields_case_insensitive():
    rec = {
        "State": "Delhi",
        "Market": "Azadpur",
        "Commodity": "Onion",
        "Arrival_Date": "09/09/2026",
        "Min_Price": "2100",
        "Max_Price": "2500",
        "Modal_Price": "2300",
    }
    fields = map_fields(rec)
    assert fields["market"] == "Azadpur"
    assert fields["modal_price"] == "2300"


def test_map_fields_missing_required_fails_loudly():
    with pytest.raises(SchemaError, match="missing required"):
        map_fields({"market": "Azadpur", "commodity": "Potato"})  # no prices/date


def test_modal_outside_range_is_accepted_without_point(seeded: Session):
    # Real Agmarknet data sometimes reports a modal outside [min, max]. We must NOT crash
    # (ck_point_within_range) — the row is kept with the range but no asserted point price.
    from sqlalchemy import select

    rec = {
        "state": "Delhi",
        "district": "Delhi",
        "market": "Azadpur",
        "commodity": "Potato",
        "variety": "Local",
        "grade": "FAQ",
        "arrival_date": "10/09/2026",
        "min_price": "1500",
        "max_price": "2000",
        "modal_price": "1000",  # modal < min!
    }
    result = AgmarknetConnector().ingest(seeded, [rec], mode="test")
    assert result.accepted == 1  # accepted, not crashed
    obs = seeded.scalars(select(PriceObservation)).all()
    assert len(obs) == 1
    assert obs[0].price_point_paise is None  # the out-of-range modal is not asserted
    assert obs[0].price_low_paise == 150000 and obs[0].price_high_paise == 200000
    # canonical falls back to the midpoint (1750/quintal -> 17.5/kg -> 1750 paise/kg)
    assert obs[0].canonical_price_paise_per_kg == 1750


def test_ingest_accepts_good_rejects_bad(seeded: Session):
    result = AgmarknetConnector().ingest(seeded, _records(), mode="test")
    assert result.rows_in == 8
    # 3 good: Azadpur Potato, Azadpur Onion, Keshopur Potato, plus mixed-case Onion = 4
    assert result.accepted == 4
    reasons = result.reason_counts
    assert any("missing_or_zero_price" in r for r in reasons)
    assert any("unresolved_commodity" in r for r in reasons)  # Dragon Fruit
    assert any("unresolved_market" in r for r in reasons)  # Some Random Mandi
    assert any("range_disorder" in r for r in reasons)  # min>max


def test_canonical_quintal_to_kg(seeded: Session):
    AgmarknetConnector().ingest(
        seeded, _records()[:1], mode="test"
    )  # Azadpur Potato modal 1350/qtl
    obs = seeded.scalars(select(PriceObservation)).all()
    assert len(obs) == 1
    o = obs[0]
    assert o.unit_raw == "Quintal"
    assert o.price_point_paise == 135000  # 1350 rupees/quintal in paise
    assert o.canonical_price_paise_per_kg == 1350  # /100 kg = 13.50 rupees/kg
    assert o.source_url.startswith("https://api.data.gov.in/resource/")
    assert "Potato" in o.raw_quote


def test_run_records_ingest_run(seeded: Session):
    connector = AgmarknetConnector(raw_dir=Path("/tmp/vervana_test_raw"))
    connector.fetch_raw = lambda **_: _records()  # bypass network
    run, result = connector.run(seeded, mode="daily")
    assert run.status == "ok"
    assert run.rows_in == 8
    assert run.accepted == 4
    assert run.rejection_reasons  # dict of reason->count persisted


def test_fetch_failure_leaves_no_partial_data(seeded: Session):
    connector = AgmarknetConnector()

    def boom(**_):
        raise RuntimeError("network down")

    connector.fetch_raw = boom
    with pytest.raises(RuntimeError, match="network down"):
        connector.run(seeded, mode="daily")
    # No observations written, and the failed run is recorded.
    assert seeded.scalar(select(func.count()).select_from(PriceObservation)) == 0
    failed = seeded.scalars(select(IngestRun).where(IngestRun.status == "failed")).all()
    assert len(failed) == 1
    assert "network down" in failed[0].error


def test_connector_disabled_via_config(monkeypatch):
    from vervana.config import Settings

    monkeypatch.setenv("VERVANA_DISABLED_CONNECTORS", "agmarknet,youtube")
    settings = Settings(_env_file=None)
    assert AgmarknetConnector().enabled(settings) is False


def test_missing_api_key_raises(monkeypatch, seeded: Session):
    from vervana.config import Settings
    from vervana.connectors.agmarknet import MissingApiKeyError

    monkeypatch.delenv("VERVANA_DATA_GOV_IN_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(MissingApiKeyError):
        AgmarknetConnector().fetch_raw(settings=settings)
