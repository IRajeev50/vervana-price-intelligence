"""Commodity study: lot-free analysis of any commodity (The Book).

Offline. The study runs the same honesty gate as the lot view on a commodity's best-covered
market, with a price landscape across markets — no stored lot required.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from vervana.book.service import study_commodities, study_commodity
from vervana.db.base import SourceClass, TimeBasis
from vervana.models.entities import Commodity, Market
from vervana.repository.prices import insert_observation
from vervana.time import IST


def _market(session, name, state="X"):
    m = Market(canonical_name=name, city=name, state=state)
    session.add(m)
    session.flush()
    return m


def _price(session, commodity_id, market_id, rupees, day=10):
    insert_observation(
        session,
        commodity_id=commodity_id,
        market_id=market_id,
        source_class=SourceClass.executed_summary,
        price_low_paise=int(rupees * 100),
        price_high_paise=int(rupees * 100),
        unit_raw="Quintal",
        canonical_price_paise_per_kg=int(rupees * 100),
        source_url="https://x",
        raw_quote="{}",
        observed_at=datetime(2026, 11, day, tzinfo=IST),
        time_basis=TimeBasis.daily_summary,
    )


def test_unknown_commodity_is_not_guessed(session: Session):
    st = study_commodity(session, "Dragonfruit")
    assert st.decision.verdict == "WAIT"
    assert "not a known commodity" in st.decision.why


def test_known_commodity_without_prices_waits(session: Session):
    session.add(Commodity(canonical_name="Onion"))
    session.flush()
    st = study_commodity(session, "Onion")
    assert st.decision.verdict == "WAIT"
    assert st.market is None
    assert "nothing to study" in st.decision.why


def test_study_picks_best_covered_market_and_landscape(session: Session):
    c = Commodity(canonical_name="Onion")
    session.add(c)
    session.flush()
    deep = _market(session, "Lasalgaon", "Maharashtra")
    thin = _market(session, "Pune(Moshi)", "Maharashtra")
    # deep market gets several distinct days; thin gets one, at a different price.
    for day in range(1, 6):
        _price(session, c.id, deep.id, 30.0, day=day)
    _price(session, c.id, thin.id, 50.0, day=2)

    st = study_commodity(session, "Onion", horizon_days=14)
    assert st.market == "Lasalgaon"  # best-covered market anchors the study
    assert st.n_markets == 2
    # Landscape = latest price per market: {30, 50} -> lo 30, hi 50.
    assert st.price_lo_paise == 3000
    assert st.price_hi_paise == 5000
    # No band has cleared the kill bar in a fresh store -> honest WAIT.
    assert st.decision.verdict == "WAIT"
    assert st.decision.evidence  # the full rationale is populated


def test_study_commodities_lists_only_those_with_executed_prices(session: Session):
    c = Commodity(canonical_name="Onion")
    other = Commodity(canonical_name="Mango")  # no prices
    session.add_all([c, other])
    session.flush()
    m = _market(session, "Lasalgaon", "Maharashtra")
    _price(session, c.id, m.id, 30.0)

    listed = study_commodities(session)
    assert "Onion" in listed
    assert "Mango" not in listed
