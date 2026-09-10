"""M6 transcript connector: quote_indicative, digit-merge + range-sanity flags, no fetch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.connectors.transcript import TranscriptConnector
from vervana.db.base import SourceClass
from vervana.models.observations import PriceObservation
from vervana.repository.registry import seed_registry

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def _row(commodity, channel, low, high=None, flag=""):
    return {
        "Date": "2026-07-01",
        "Day": "Wed",
        "Channel / Mandi": channel,
        "Commodity": commodity,
        "Variety / Origin (as quoted)": "",
        "Price Low": low,
        "Price High": high,
        "Unit": "",
        "Arrivals (trucks)": "",
        "Carryover": "",
        "Market Commentary": "",
        "Raw Quote (transcript)": "quote text",
        "Source Video": "https://youtu.be/x",
        "Flag": flag,
    }


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def test_no_fetch_path():
    with pytest.raises(NotImplementedError):
        TranscriptConnector().fetch_raw()


def test_ingest_video_quotes(seeded: Session):
    records = [
        _row("Onion", "Delhi Fruit Market (Azadpur Mandi)", 40, 50),
        _row("Potato", "The Solanki Vlog (Keshopur Mandi)", 1415, None, "possible merged digits"),
        _row("Vegetables (all)", "Delhi Fruit Market (Azadpur Mandi)", 10, 20),  # unresolved
        _row("Tomato", "Delhi Fruit Market (Azadpur Mandi)", None, None),  # no price
        _row("Onion", "Delhi Fruit Market (Azadpur Mandi)", 800, 112000),  # implausible
    ]
    result = TranscriptConnector().ingest(seeded, records, mode="test")
    assert result.accepted == 3  # onion, potato, implausible-but-stored
    assert any("unresolved_commodity" in r for r in result.reason_counts)
    assert any("no_price" in r for r in result.reason_counts)

    obs = seeded.scalars(
        select(PriceObservation).where(
            PriceObservation.source_class == SourceClass.quote_indicative
        )
    ).all()
    # all video quotes; unit unstated -> canonical NULL (never guessed)
    assert all(o.unit_raw == "unstated" for o in obs)
    assert all(o.canonical_price_paise_per_kg is None for o in obs)

    flags = [json.loads(o.raw_quote)["detected_flags"] for o in obs]
    assert any(any("digit_merge_suspected" in f for f in fl) for fl in flags)
    assert any(any("range_implausible_ratio" in f for f in fl) for fl in flags)


def test_video_quotes_not_blended_with_wholesale(seeded: Session):
    from datetime import datetime

    from vervana.db.base import TimeBasis
    from vervana.repository.prices import (
        MixedSourceClassError,
        insert_observation,
        mean_canonical_price_paise_per_kg,
    )
    from vervana.time import IST

    TranscriptConnector().ingest(
        seeded, [_row("Onion", "Delhi Fruit Market (Azadpur Mandi)", 40, 50)], mode="t"
    )
    q = seeded.scalar(select(PriceObservation))
    insert_observation(
        seeded,
        commodity_id=q.commodity_id,
        market_id=q.market_id,
        source_class=SourceClass.executed_summary,
        price_low_paise=2000,
        price_high_paise=2200,
        unit_raw="Quintal",
        canonical_price_paise_per_kg=2100,
        source_url="https://x",
        raw_quote="{}",
        observed_at=datetime(2026, 7, 1, tzinfo=IST),
        time_basis=TimeBasis.daily_summary,
    )
    allrows = seeded.scalars(
        select(PriceObservation).where(PriceObservation.commodity_id == q.commodity_id)
    ).all()
    with pytest.raises(MixedSourceClassError):
        mean_canonical_price_paise_per_kg(allrows)
