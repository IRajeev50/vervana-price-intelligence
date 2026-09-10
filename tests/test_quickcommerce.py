"""Quick-commerce connector: CSV import, ₹/kg normalisation, no-scraper guard, digest."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.connectors.quickcommerce import QuickCommerceConnector, ScraperForbiddenError
from vervana.db.base import SourceClass
from vervana.digest import build_digest
from vervana.models.observations import PriceObservation
from vervana.models.retail import RetailOfferDetail
from vervana.repository.registry import seed_registry

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
SAMPLE = Path(__file__).resolve().parent.parent / "data" / "samples" / "qcomm_sample.csv"


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def test_no_scraper_path():
    with pytest.raises(ScraperForbiddenError):
        QuickCommerceConnector().fetch_raw()


def test_csv_import_normalises_to_kg(seeded: Session):
    result = QuickCommerceConnector().import_csv(seeded, SAMPLE)
    assert result.accepted == 6
    # Tomato 500 g pack at ₹29 -> ₹58/kg (5800 paise).
    obs = seeded.scalars(
        select(PriceObservation).where(PriceObservation.source_class == SourceClass.retail_offer)
    ).all()
    tomato = next(o for o in obs if o.canonical_price_paise_per_kg == 5800)
    assert tomato.unit_raw == "500 g"
    detail = seeded.scalar(
        select(RetailOfferDetail).where(RetailOfferDetail.observation_id == tomato.id)
    )
    assert detail.platform == "Blinkit"
    assert detail.selling_price_paise == 2900  # ₹29
    assert float(detail.pack_kg) == 0.5


def test_retail_not_averaged_with_wholesale(seeded: Session):
    # The guard still blocks blending retail with wholesale (source-class guard).
    from datetime import datetime

    from vervana.db.base import TimeBasis
    from vervana.repository.prices import (
        MixedSourceClassError,
        insert_observation,
        mean_canonical_price_paise_per_kg,
    )
    from vervana.time import IST

    QuickCommerceConnector().import_csv(seeded, SAMPLE)
    potato = seeded.scalar(
        select(PriceObservation).where(PriceObservation.source_class == SourceClass.retail_offer)
    )
    # add a wholesale row for the same commodity
    insert_observation(
        seeded,
        commodity_id=potato.commodity_id,
        market_id=potato.market_id,
        source_class=SourceClass.executed_summary,
        price_low_paise=1500,
        price_high_paise=2000,
        unit_raw="Quintal",
        canonical_price_paise_per_kg=1800,
        source_url="https://x",
        raw_quote="{}",
        observed_at=datetime(2026, 9, 10, tzinfo=IST),
        time_basis=TimeBasis.daily_summary,
    )
    both = seeded.scalars(
        select(PriceObservation).where(PriceObservation.commodity_id == potato.commodity_id)
    ).all()
    with pytest.raises(MixedSourceClassError):
        mean_canonical_price_paise_per_kg(both)


def test_digest_shows_spread_and_disclaimers(seeded: Session):
    QuickCommerceConnector().import_csv(seeded, SAMPLE)
    text = build_digest(seeded, ["Potato", "Onion"])
    assert "HoReCa procurement digest" in text
    assert "retail" in text and "Blinkit" in text
    assert "Not trading advice" in text
    assert "never averaged" in text
