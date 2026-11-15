"""M19a: the Book's destination riverine flood flag — wiring + honesty.

Offline. Proves the market->destination-zone map, the access-pending honesty line, a
recorded overlay driving the flood-driven REROUTE end-to-end, and that a reroute never
moves into another flood-exposed hub. Riverine-only throughout.
"""

from __future__ import annotations

from datetime import datetime

from vervana.book.service import (
    _destination_flood,
    _market_is_flood_exposed,
    decide_for_lot,
)
from vervana.db.base import SourceClass, TimeBasis
from vervana.models.entities import Commodity, Market
from vervana.repository.flood_overlay import record_overlays
from vervana.repository.inventory import add_lot
from vervana.repository.prices import insert_observation
from vervana.supply.destination_zones import zone_for_market
from vervana.supply.floodhub import FloodOverlay
from vervana.time import IST

# --- zone mapping ----------------------------------------------------------

def test_zone_for_market_maps_delhi_hubs_only():
    z = zone_for_market("Azadpur")
    assert z is not None and z.zone == "delhi-yamuna"
    assert zone_for_market("Lasalgaon") is None  # a growing belt, not a destination hub
    assert zone_for_market("") is None


# --- helpers ---------------------------------------------------------------

def _market(session, name, state, lat, lon):
    m = Market(canonical_name=name, city=name, state=state, latitude=lat, longitude=lon)
    session.add(m)
    session.flush()
    return m


def _price(session, commodity_id, market_id, rupees):
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
        observed_at=datetime(2026, 11, 10, tzinfo=IST),
        time_basis=TimeBasis.daily_summary,
    )


def _overlay(session, zone, severity):
    record_overlays(
        session,
        [FloodOverlay(zone, severity, "RISE", datetime(2026, 11, 12, tzinfo=IST), None, None)],
        source="Operator-recorded from CWC bulletin",
        source_url="https://cwc.gov.in/bulletin",
    )


# --- access-pending honesty ------------------------------------------------

def test_destination_flood_access_pending_is_not_no_risk(session):
    _market(session, "Azadpur", "Delhi", 28.71, 77.17)
    flag, line = _destination_flood(session, "Azadpur")
    assert flag is None  # no overlay -> no flag
    assert "access pending" in line and "NOT 'no flood risk'" in line


def test_destination_flood_unmapped_market(session):
    flag, line = _destination_flood(session, "Lasalgaon")
    assert flag is None
    assert "not in a mapped flood zone" in line


def test_recorded_overlay_becomes_a_risk_flag(session):
    _market(session, "Azadpur", "Delhi", 28.71, 77.17)
    _overlay(session, "delhi-yamuna", "SEVERE")
    flag, line = _destination_flood(session, "Azadpur")
    assert flag is not None and flag.is_risk and flag.severity == "SEVERE"
    assert "delhi-yamuna" in line and "SEVERE" in line
    # A reroute into any other delhi-yamuna hub is flagged exposed; an inland mandi is not.
    assert _market_is_flood_exposed(session, "Okhla") is True
    assert _market_is_flood_exposed(session, "PMY Kullu") is False


# --- end-to-end flood-driven REROUTE ---------------------------------------

def test_flood_on_destination_reroutes_to_a_safe_inland_mandi(session):
    c = Commodity(canonical_name="Capsicum")
    session.add(c)
    session.flush()
    azadpur = _market(session, "Azadpur", "Delhi", 28.71, 77.17)
    kullu = _market(session, "PMY Kullu", "Himachal Pradesh", 31.9578, 77.1095)
    _price(session, c.id, azadpur.id, 30.0)
    _price(session, c.id, kullu.id, 35.0)  # safe inland alt, near the warehouse
    _overlay(session, "delhi-yamuna", "SEVERE")

    # Warehouse sits by Kullu, so rerouting there carries ~no freight; Azadpur is far.
    lot = add_lot(
        session,
        commodity_id=c.id,
        quantity_kg=3000,
        purchase_price_paise_per_kg=5500,
        purchase_date=datetime(2026, 11, 8, tzinfo=IST).date(),
        warehouse="Kullu pack-house",
        warehouse_lat=31.9578,
        warehouse_lon=77.1095,
        intended_market_id=azadpur.id,
    )

    ctx = decide_for_lot(session, lot, horizon_days=14)
    assert ctx.decision.verdict == "REROUTE"
    assert "flood-exposed" in ctx.decision.why
    assert "PMY Kullu" in ctx.decision.why
    assert "delhi-yamuna" in ctx.flood_line and "SEVERE" in ctx.flood_line
