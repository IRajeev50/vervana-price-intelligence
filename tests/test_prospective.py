"""Prospective forecast log: record forward call, score against actuals, aggregate."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass, TimeBasis
from vervana.forecast.runner import (
    prospective_summary,
    record_prospective,
    score_due,
    video_actual_lookup,
)
from vervana.models.entities import Commodity, Market
from vervana.models.forecast_log import ProspectiveForecast
from vervana.repository.prices import insert_observation
from vervana.repository.registry import seed_registry
from vervana.time import IST, now_utc, to_ist

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def _ids(session):
    cid = session.scalar(select(Commodity.id).where(Commodity.canonical_name == "Onion"))
    mid = session.scalar(select(Market.id).where(Market.canonical_name == "Azadpur"))
    return cid, mid


def test_record_and_score(seeded: Session):
    cid, mid = _ids(seeded)
    # A forecast whose target date is already in the past, so it can be scored now.
    target = to_ist(now_utc()).date() - timedelta(days=1)
    seeded.add(
        ProspectiveForecast(
            commodity_id=cid,
            market_id=mid,
            target_date=target,
            made_at=now_utc(),
            model="seasonal_naive",
            point_paise=4000,
            low_paise=3500,
            high_paise=4500,
        )
    )
    seeded.flush()
    # The realised video price on the target date is ₹41/kg (within the interval).
    insert_observation(
        seeded,
        commodity_id=cid,
        market_id=mid,
        source_class=SourceClass.quote_indicative,
        price_low_paise=4100,
        price_high_paise=4100,
        unit_raw="unstated",
        source_url="https://youtu.be/x",
        raw_quote="{}",
        observed_at=datetime(target.year, target.month, target.day, tzinfo=IST),
        time_basis=TimeBasis.single_daily_quote,
    )
    n = score_due(seeded, video_actual_lookup(seeded))
    assert n == 1
    f = seeded.scalar(select(ProspectiveForecast))
    assert f.actual_paise == 4100
    assert f.hit_interval is True
    assert f.abs_error_paise == 100

    summary = prospective_summary(seeded)
    assert summary["n_calls"] == 1 and summary["n_scored"] == 1
    assert summary["interval_hit_rate"] == 1.0


def test_record_prospective_makes_future_call(seeded: Session):
    import numpy as np

    cid, mid = _ids(seeded)
    record_prospective(
        seeded,
        commodity_id=cid,
        market_id=mid,
        model="naive",
        series=np.array([4000.0] * 20),
    )
    f = seeded.scalar(select(ProspectiveForecast))
    assert f.target_date == to_ist(now_utc()).date() + timedelta(days=1)
    assert f.actual_paise is None  # future, unscored
    assert f.point_paise == 4000


def test_summary_empty(seeded: Session):
    s = prospective_summary(seeded)
    assert s["n_calls"] == 0 and s["mae_rupees"] is None
