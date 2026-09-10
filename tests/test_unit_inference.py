"""Video-quote unit inference: kg vs quintal, and honest 'unknown'."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.analytics.unit_inference import infer_units
from vervana.db.base import SourceClass, TimeBasis
from vervana.models.entities import Commodity, Market
from vervana.repository.prices import insert_observation
from vervana.repository.registry import seed_registry
from vervana.time import IST

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def _ids(session, commodity):
    cid = session.scalar(select(Commodity.id).where(Commodity.canonical_name == commodity))
    az = session.scalar(select(Market.id).where(Market.canonical_name == "Azadpur"))
    return cid, az


def _video(session, commodity, paise):
    cid, az = _ids(session, commodity)
    insert_observation(
        session,
        commodity_id=cid,
        market_id=az,
        source_class=SourceClass.quote_indicative,
        price_low_paise=paise,
        price_high_paise=paise,
        unit_raw="unstated",
        source_url="https://youtu.be/x",
        raw_quote="{}",
        observed_at=datetime(2026, 7, 1, tzinfo=IST),
        time_basis=TimeBasis.single_daily_quote,
    )


def _agmarknet(session, commodity, canonical_paise):
    cid, az = _ids(session, commodity)
    insert_observation(
        session,
        commodity_id=cid,
        market_id=az,
        source_class=SourceClass.executed_summary,
        price_low_paise=canonical_paise * 100,
        price_high_paise=canonical_paise * 100,
        unit_raw="Quintal",
        canonical_price_paise_per_kg=canonical_paise,
        source_url="https://x",
        raw_quote="{}",
        observed_at=datetime(2026, 7, 1, tzinfo=IST),
        time_basis=TimeBasis.daily_summary,
    )


def test_infer_kg(seeded: Session):
    _video(seeded, "Onion", 4000)  # ₹40 (per kg)
    _agmarknet(seeded, "Onion", 2300)  # ₹23/kg
    u = infer_units(seeded)["Onion"]
    assert u.inferred_unit == "kg"
    assert u.scale_to_kg == 1.0


def test_infer_quintal(seeded: Session):
    _video(seeded, "Tomato", 150000)  # ₹1500 (per quintal)
    _agmarknet(seeded, "Tomato", 1500)  # ₹15/kg  -> ratio 100x
    u = infer_units(seeded)["Tomato"]
    assert u.inferred_unit == "quintal"
    assert u.scale_to_kg == 1 / 100


def test_infer_unknown_when_ambiguous(seeded: Session):
    _video(seeded, "Potato", 30000)  # ₹300 midpoint
    _agmarknet(seeded, "Potato", 1500)  # ₹15/kg -> ratio 20x -> quintal boundary
    _video(seeded, "Onion", 25000)  # ₹250
    _agmarknet(seeded, "Onion", 1500)  # ratio ~16x -> ambiguous -> unknown
    u = infer_units(seeded)["Onion"]
    assert u.inferred_unit == "unknown"
    assert u.scale_to_kg is None


def test_plausibility_without_agmarknet(seeded: Session):
    _video(seeded, "Garlic", 8000)  # ₹80 plausible per kg, no agmarknet ref
    u = infer_units(seeded)["Garlic"]
    assert u.inferred_unit == "kg"
