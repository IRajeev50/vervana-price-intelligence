"""Sourcing layer: state-centroid distance, landed-cost ranking, and the directory.

Offline: in-memory SQLite. The landed cost = real wholesale + an estimated
freight; these tests pin the ordering logic (freight can change who is cheapest)
and the provenance guard on directory rows.
"""

from __future__ import annotations

from datetime import datetime

from vervana.db.base import SourceClass, TimeBasis
from vervana.geo import canonical_state, state_distance_km
from vervana.models.entities import Commodity, Market
from vervana.repository.prices import insert_observation
from vervana.repository.sourcing import (
    add_buyer,
    add_supplier_contact,
    landed_cost_ranking,
    list_buyers,
    supplier_contacts,
)
from vervana.time import IST


def test_state_distance_and_aliases():
    assert state_distance_km("Delhi", "Delhi") == 0.0  # same state -> coarse 0
    assert state_distance_km("Delhi", "Tamil Nadu") > 1000
    assert state_distance_km("Delhi", "Atlantis") is None  # unknown -> not guessed
    assert canonical_state("Orissa") == "Odisha"
    assert canonical_state("Jammu and Kashmir") == "Jammu & Kashmir"


def _coconut_in(session, market_name, state, rupees_per_kg):
    c = session.scalar(select_commodity(session, "Coconut"))
    m = Market(canonical_name=market_name, city=market_name, state=state)
    session.add(m)
    session.flush()
    insert_observation(
        session,
        commodity_id=c.id,
        market_id=m.id,
        source_class=SourceClass.executed_summary,
        price_low_paise=int(rupees_per_kg * 100),
        price_high_paise=int(rupees_per_kg * 100),
        unit_raw="Quintal",
        canonical_price_paise_per_kg=int(rupees_per_kg * 100),
        source_url="https://x",
        raw_quote="{}",
        observed_at=datetime(2026, 9, 20, tzinfo=IST),
        time_basis=TimeBasis.daily_summary,
    )


def select_commodity(session, name):
    from sqlalchemy import select

    return select(Commodity).where(Commodity.canonical_name == name)


def test_freight_can_change_the_cheapest(session):
    session.add(Commodity(canonical_name="Coconut"))
    session.flush()
    # Same source price, different distance from a Delhi buyer: Karnataka is nearer
    # than Tamil Nadu, so it must win on landed cost.
    _coconut_in(session, "Vaniyampadi", "Tamil Nadu", 20.0)
    _coconut_in(session, "Gubbi APMC", "Karnataka", 20.0)
    res = landed_cost_ranking(session, "Coconut", "Delhi", rate_per_tonne_km=4.0)

    assert res["n_markets"] == 2
    assert res["cheapest_source"]["wholesale_paise"] == 2000
    assert res["rows"][0]["state"] == "Karnataka"  # nearer -> cheaper delivered
    # Landed cost is strictly wholesale + a positive freight (both are far from Delhi).
    top = res["rows"][0]
    assert top["landed_paise"] > top["wholesale_paise"]
    assert top["freight_rupees"] > 0
    # Source-cheapest (a tie here) differs from delivered-cheapest ordering by distance.
    assert res["cheapest_delivered"]["market"] == "Gubbi APMC"


def test_unknown_buyer_state_falls_back_to_source_order(session):
    session.add(Commodity(canonical_name="Coconut"))
    session.flush()
    _coconut_in(session, "A mandi", "Karnataka", 25.0)
    _coconut_in(session, "B mandi", "Karnataka", 20.0)
    res = landed_cost_ranking(session, "Coconut", None, rate_per_tonne_km=4.0)
    assert res["buyer_state_known"] is False
    # No landed cost computed; ordering falls back to wholesale ascending.
    assert res["rows"][0]["market"] == "B mandi"
    assert res["rows"][0]["landed_rupees"] is None


def test_directory_rows_require_provenance(session):
    bid = add_buyer(session, name="Test Kitchen", state="Delhi", commodities="Onion, Tomato")
    assert bid
    buyers = list_buyers(session)
    assert buyers[0]["name"] == "Test Kitchen"
    assert "Onion" in buyers[0]["commodities"] and "Tomato" in buyers[0]["commodities"]

    m = Market(canonical_name="Z mandi", city="Z", state="Karnataka")
    session.add(m)
    session.flush()
    add_supplier_contact(
        session, market_id=m.id, contact_name="Ravi", phone="123", source="mandi board"
    )
    contacts = supplier_contacts(session, m.id)
    assert contacts[0].contact_name == "Ravi"
    assert contacts[0].source  # provenance is never blank


def test_self_registration_creates_self_listed_suppliers(tmp_path, monkeypatch):
    """A supplier lists themselves via the open form; entry is marked self-listed."""
    from datetime import datetime

    from fastapi.testclient import TestClient

    from vervana.db.base import Base, TimeBasis
    from vervana.db.engine import make_engine, session_scope
    from vervana.repository.sourcing import list_suppliers

    url = f"sqlite:///{tmp_path / 'reg.sqlite3'}"
    monkeypatch.setenv("VERVANA_DATABASE_URL", url)
    Base.metadata.create_all(make_engine(url))
    with session_scope() as s:
        c = Commodity(canonical_name="Onion")
        m = Market(canonical_name="Azadpur", city="Delhi", state="Delhi")
        s.add_all([c, m])
        s.flush()
        insert_observation(
            s,
            commodity_id=c.id,
            market_id=m.id,
            source_class=SourceClass.executed_summary,
            price_low_paise=1000,
            price_high_paise=1000,
            unit_raw="Quintal",
            canonical_price_paise_per_kg=1000,
            source_url="https://x",
            raw_quote="{}",
            observed_at=datetime(2026, 9, 20, tzinfo=IST),
            time_basis=TimeBasis.daily_summary,
        )

    from vervana.web.app import app

    client = TestClient(app)
    ok = client.post(
        "/sourcing/register",
        data={
            "name": "Test Growers",
            "phone": "9990001234",
            "state": "Delhi",
            "commodity": ["Onion"],
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303 and "ok=" in ok.headers["location"]
    with session_scope() as s:
        rows = list_suppliers(s, "Onion")
    listed = next(r for r in rows if r["name"] == "Test Growers")
    assert listed["source"].startswith("Self-registered")  # provenance says self-listed
    assert listed["phone"] == "9990001234"

    # No contact -> rejected, nothing added (a listing with no way to reach it is useless).
    bad = client.post(
        "/sourcing/register",
        data={"name": "No Contact", "commodity": ["Onion"]},
        follow_redirects=False,
    )
    assert bad.status_code == 303 and "err=" in bad.headers["location"]
    with session_scope() as s:
        assert not any(r["name"] == "No Contact" for r in list_suppliers(s, "Onion"))
