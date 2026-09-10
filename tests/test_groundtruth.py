"""M5 ground-truth study: deviation math, interim vs real mode, R3 verdict."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from vervana.analytics.groundtruth import (
    CommodityDeviation,
    PricePoint,
    _deviation,
    r3_verdict,
    run_study,
)
from vervana.db.base import SourceClass, TimeBasis
from vervana.models.entities import Commodity, Market
from vervana.models.invoice import Invoice
from vervana.repository.prices import insert_observation
from vervana.repository.registry import seed_registry
from vervana.time import IST

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
D = date(2026, 9, 8)


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def test_deviation_math():
    ref = [PricePoint("Onion", D, 4200.0)]
    comp = [PricePoint("Onion", D, 4000.0)]
    out = _deviation(ref, comp)
    assert len(out) == 1
    assert out[0].commodity == "Onion"
    assert abs(out[0].mapd - (200 / 4200)) < 1e-9


def test_interim_mode_without_invoices(seeded: Session):
    result = run_study(seeded)
    assert result.mode == "interim"
    assert "PENDING" in r3_verdict(result)
    assert any("NOT the ground-truth verdict" in c for c in result.caveats)


def _add_video(session, commodity, low, high, on=D):
    cid = session.scalar(
        __import__("sqlalchemy").select(Commodity.id).where(Commodity.canonical_name == commodity)
    )
    mid = session.scalar(
        __import__("sqlalchemy").select(Market.id).where(Market.canonical_name == "Azadpur")
    )
    insert_observation(
        session,
        commodity_id=cid,
        market_id=mid,
        source_class=SourceClass.quote_indicative,
        price_low_paise=low,
        price_high_paise=high,
        unit_raw="unstated",
        source_url="https://youtu.be/x",
        raw_quote="{}",
        observed_at=__import__("datetime").datetime(on.year, on.month, on.day, tzinfo=IST),
        time_basis=TimeBasis.single_daily_quote,
    )
    return cid, mid


def test_real_mode_r3_holds(seeded: Session):
    cid, mid = _add_video(seeded, "Onion", 4000, 4000)  # video midpoint ₹40/kg
    seeded.add(Invoice(commodity_id=cid, market_id=mid, invoice_date=D, price_paise_per_kg=4200))
    seeded.flush()
    result = run_study(seeded)
    assert result.mode == "real"
    assert "HOLDS" in r3_verdict(result)  # 4.8% deviation < 10%


def test_real_mode_r3_fails(seeded: Session):
    cid, mid = _add_video(seeded, "Onion", 4000, 4000)  # ₹40/kg
    seeded.add(Invoice(commodity_id=cid, market_id=mid, invoice_date=D, price_paise_per_kg=8000))
    seeded.flush()
    result = run_study(seeded)
    assert result.mode == "real"
    assert "FAILS" in r3_verdict(result)  # 50% deviation > 10%


def test_deviation_type():
    assert isinstance(_deviation([], [])[:], list)
    assert CommodityDeviation("x", 1, 0.1).mapd == 0.1
