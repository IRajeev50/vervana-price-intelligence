"""The source-class guard + provenance/range/append-only invariants (M1 DoD #1)."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass, TimeBasis
from vervana.repository.prices import (
    MixedSourceClassError,
    average_canonical_price,
    insert_observation,
    mean_canonical_price_paise_per_kg,
    observations_for_commodity_on_date,
    supersede,
)
from vervana.time import IST

OBS_DATE = date(2026, 9, 10)


def _obs_kwargs(commodity_id, market_id, source_class, *, low, high, canonical, **over):
    base = dict(
        commodity_id=commodity_id,
        market_id=market_id,
        source_class=source_class,
        price_low_paise=low,
        price_high_paise=high,
        unit_raw="kg",
        canonical_price_paise_per_kg=canonical,
        source_url="https://example.test/evidence",
        raw_quote="aloo 20-22 rupaye kilo",
        observed_at=datetime(2026, 9, 10, 10, 0, tzinfo=IST),
        time_basis=TimeBasis.daily_summary,
    )
    base.update(over)
    return base


def test_naive_average_across_classes_is_blocked(potato_and_market, session: Session):
    """The headline guard: mixing a wholesale quote and a retail offer is refused."""
    cid, mid = potato_and_market
    insert_observation(
        session,
        **_obs_kwargs(cid, mid, SourceClass.quote_indicative, low=2000, high=2200, canonical=2100),
    )
    insert_observation(
        session,
        **_obs_kwargs(cid, mid, SourceClass.retail_offer, low=4000, high=4500, canonical=4200),
    )

    # A naive "average potato price today" pulls all classes...
    all_today = observations_for_commodity_on_date(session, commodity_id=cid, on_date=OBS_DATE)
    assert len(all_today) == 2
    # ...and the guard refuses to blend them.
    with pytest.raises(MixedSourceClassError):
        mean_canonical_price_paise_per_kg(all_today)


def test_class_scoped_average_works(potato_and_market, session: Session):
    cid, mid = potato_and_market
    insert_observation(
        session,
        **_obs_kwargs(cid, mid, SourceClass.quote_indicative, low=2000, high=2200, canonical=2000),
    )
    insert_observation(
        session,
        **_obs_kwargs(cid, mid, SourceClass.quote_indicative, low=2200, high=2400, canonical=2400),
    )
    avg = average_canonical_price(
        session, commodity_id=cid, source_class=SourceClass.quote_indicative, on_date=OBS_DATE
    )
    assert avg == 2200  # (2000 + 2400) / 2


def test_superseded_rows_are_excluded(potato_and_market, session: Session):
    cid, mid = potato_and_market
    old = insert_observation(
        session,
        **_obs_kwargs(cid, mid, SourceClass.quote_indicative, low=2000, high=2000, canonical=2000),
    )
    supersede(
        session,
        old.id,
        reason="typo in original",
        **_obs_kwargs(cid, mid, SourceClass.quote_indicative, low=3000, high=3000, canonical=3000),
    )
    avg = average_canonical_price(
        session, commodity_id=cid, source_class=SourceClass.quote_indicative, on_date=OBS_DATE
    )
    assert avg == 3000  # old (2000) excluded; only the correction counts


def test_provenance_is_required(potato_and_market, session: Session):
    cid, mid = potato_and_market
    with pytest.raises(IntegrityError):
        insert_observation(
            session,
            **_obs_kwargs(
                cid,
                mid,
                SourceClass.quote_indicative,
                low=2000,
                high=2200,
                canonical=2100,
                source_url="   ",  # blank provenance must fail insertion
            ),
        )


def test_range_must_be_ordered(potato_and_market, session: Session):
    cid, mid = potato_and_market
    with pytest.raises(IntegrityError):
        insert_observation(
            session,
            **_obs_kwargs(
                cid, mid, SourceClass.quote_indicative, low=2500, high=2000, canonical=2200
            ),
        )


def test_unknown_unit_leaves_canonical_null_and_is_unaveraged(potato_and_market, session: Session):
    cid, mid = potato_and_market
    insert_observation(
        session,
        **_obs_kwargs(
            cid,
            mid,
            SourceClass.quote_indicative,
            low=2000,
            high=2200,
            canonical=None,
            unit_raw="bag",  # unknown weight -> canonical NULL, we don't guess
        ),
    )
    obs = observations_for_commodity_on_date(session, commodity_id=cid, on_date=OBS_DATE)
    with pytest.raises(ValueError, match="canonical"):
        mean_canonical_price_paise_per_kg(obs)
