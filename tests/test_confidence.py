"""§5.4 confidence: base composite + cross-source agreement (within one class only)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.confidence import agreement_factor, price_confidence, price_confidence_full
from vervana.db.base import SourceClass, TimeBasis
from vervana.models.entities import Commodity, Market
from vervana.repository.prices import insert_observation
from vervana.repository.registry import seed_registry
from vervana.time import IST

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
D = date(2026, 9, 8)


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def _obs(session, canonical, cls=SourceClass.executed_summary):
    cid = session.scalar(select(Commodity.id).where(Commodity.canonical_name == "Onion"))
    mid = session.scalar(select(Market.id).where(Market.canonical_name == "Azadpur"))
    return insert_observation(
        session,
        commodity_id=cid,
        market_id=mid,
        source_class=cls,
        price_low_paise=canonical,
        price_high_paise=canonical,
        unit_raw="Quintal",
        canonical_price_paise_per_kg=canonical,
        source_url="https://x",
        raw_quote="{}",
        observed_at=datetime(D.year, D.month, D.day, tzinfo=IST),
        time_basis=TimeBasis.daily_summary,
    )


def test_base_confidence():
    class Fake:
        source_class = SourceClass.executed_summary
        unit_conversion_confidence = 1.0

    assert price_confidence(Fake()) == 0.8  # reliability 0.8 × conv 1.0


def test_agreement_no_peers_is_neutral(seeded: Session):
    o = _obs(seeded, 2000)
    factor, basis = agreement_factor(seeded, o)
    assert factor == 1.0
    assert "no same-class peers" in basis


def test_agreement_penalises_outlier(seeded: Session):
    _obs(seeded, 2000)  # peers cluster near ₹20/kg
    _obs(seeded, 2100)
    outlier = _obs(seeded, 4000)  # ₹40/kg — 90%+ off peer median
    factor, _ = agreement_factor(seeded, outlier)
    assert factor < 1.0  # penalised
    full, _ = price_confidence_full(seeded, outlier)
    assert full < 0.8  # below the base composite


def test_agreement_only_within_class(seeded: Session):
    # A retail_offer must NOT count as a peer of a wholesale quote (guard-respecting).
    _obs(seeded, 2000, cls=SourceClass.executed_summary)
    retail = _obs(seeded, 9000, cls=SourceClass.retail_offer)
    factor, basis = agreement_factor(seeded, retail)
    assert factor == 1.0  # its only same-class peer set is empty
    assert "no same-class peers" in basis
