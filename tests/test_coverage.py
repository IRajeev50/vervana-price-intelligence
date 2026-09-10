"""Coverage study math + R5 verdict labelling (deterministic dates)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.analytics.coverage import compute_coverage, format_report, r5_verdict
from vervana.db.base import SourceClass, TimeBasis
from vervana.models.entities import Commodity, Market
from vervana.repository.prices import insert_observation
from vervana.repository.registry import seed_registry
from vervana.time import IST

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
START = date(2026, 9, 6)
END = date(2026, 9, 10)  # 5-day window


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def _ids(session: Session) -> tuple[int, int, int]:
    az = session.scalar(select(Market).where(Market.canonical_name == "Azadpur"))
    potato = session.scalar(select(Commodity).where(Commodity.canonical_name == "Potato"))
    onion = session.scalar(select(Commodity).where(Commodity.canonical_name == "Onion"))
    return az.id, potato.id, onion.id


def _add(session, *, commodity_id, market_id, day: date, canonical=1350):
    ts = datetime(day.year, day.month, day.day, 10, 0, tzinfo=IST)
    insert_observation(
        session,
        commodity_id=commodity_id,
        market_id=market_id,
        source_class=SourceClass.executed_summary,
        price_low_paise=120000,
        price_high_paise=150000,
        price_point_paise=135000,
        unit_raw="Quintal",
        canonical_price_paise_per_kg=canonical,
        source_url="https://api.data.gov.in/resource/x",
        raw_quote="{}",
        observed_at=ts,
        time_basis=TimeBasis.daily_summary,
        created_at=ts,  # same-day capture
    )


def test_coverage_math_and_gap_verdict(seeded: Session):
    az, potato, onion = _ids(seeded)
    days = [START + timedelta(days=i) for i in range(5)]
    for d in days:  # Potato all 5 days
        _add(seeded, commodity_id=potato, market_id=az, day=d)
    for d in days[:3]:  # Onion only 3 of 5
        _add(seeded, commodity_id=onion, market_id=az, day=d)

    report = compute_coverage(seeded, market_id=az, start=START, end=END)
    assert report.tracked_commodities == 2
    assert report.expected_commodity_days == 10  # 2 x 5
    assert report.reported_commodity_days == 8  # 5 + 3
    assert report.coverage_pct == 0.8
    assert report.same_day_coverage_pct == 0.8  # all same-day
    verdict = r5_verdict(report, is_live=False)
    assert "COVERAGE GAP" in verdict
    assert verdict.startswith("[FIXTURE DATA")  # never a real verdict without --live


def test_no_edge_verdict_when_coverage_high(seeded: Session):
    az, potato, onion = _ids(seeded)
    days = [START + timedelta(days=i) for i in range(5)]
    for d in days:  # both commodities every day => 100% same-day
        _add(seeded, commodity_id=potato, market_id=az, day=d)
        _add(seeded, commodity_id=onion, market_id=az, day=d)
    report = compute_coverage(seeded, market_id=az, start=START, end=END)
    assert report.same_day_coverage_pct == 1.0
    assert "NO COVERAGE EDGE" in r5_verdict(report, is_live=True)


def test_implausible_value_counted(seeded: Session):
    az, potato, _ = _ids(seeded)
    _add(seeded, commodity_id=potato, market_id=az, day=START, canonical=None)  # unconverted
    _add(
        seeded,
        commodity_id=potato,
        market_id=az,
        day=START + timedelta(days=1),
        canonical=99_999_999,
    )
    report = compute_coverage(seeded, market_id=az, start=START, end=END)
    assert report.implausible_values == 2


def test_no_data_verdict(seeded: Session):
    # Empty market (the real 2026-09-10 Delhi case): honest "NO DATA", never a fake gap.
    az, _, _ = _ids(seeded)
    report = compute_coverage(seeded, market_id=az, start=START, end=END)
    assert report.tracked_commodities == 0
    assert "NO DATA" in r5_verdict(report, is_live=True)


def test_format_report_renders(seeded: Session):
    az, potato, _ = _ids(seeded)
    _add(seeded, commodity_id=potato, market_id=az, day=START)
    report = compute_coverage(seeded, market_id=az, start=START, end=END)
    text = format_report(report, is_live=False)
    assert "Agmarknet coverage study" in text
    assert "VERDICT (R5)" in text
