"""Inventory repository: lot + append-only event log, derived status, partial release (M17).

In-memory SQLite via the shared `session` fixture. No network.
"""

from __future__ import annotations

from datetime import date

from vervana.models.inventory import LotEventKind
from vervana.repository.inventory import (
    add_lot,
    append_event,
    current_positions,
    lot_count,
    position_for,
)


def test_add_lot_and_initial_position(session, potato_and_market):
    commodity_id, market_id = potato_and_market
    lot = add_lot(
        session,
        commodity_id=commodity_id,
        quantity_kg=1000.0,
        purchase_price_paise_per_kg=2000,
        purchase_date=date(2026, 11, 1),
        warehouse="Azadpur cold store",
        intended_market_id=market_id,
    )
    assert lot_count(session) == 1
    pos = position_for(session, lot.id)
    assert pos is not None
    assert pos.status == LotEventKind.acquired.value
    assert pos.remaining_kg == 1000.0
    assert pos.released_kg == 0.0


def test_partial_release_reduces_remaining_and_updates_status(session, potato_and_market):
    commodity_id, _ = potato_and_market
    lot = add_lot(
        session,
        commodity_id=commodity_id,
        quantity_kg=1000.0,
        purchase_price_paise_per_kg=2000,
        purchase_date=date(2026, 11, 1),
    )
    append_event(
        session,
        lot.id,
        LotEventKind.released,
        quantity_kg=300.0,
        price_paise_per_kg=2500,
        event_date=date(2026, 11, 10),
        note="partial sale to buyer A",
    )
    pos = position_for(session, lot.id)
    assert pos.released_kg == 300.0
    assert pos.remaining_kg == 700.0
    assert pos.status == LotEventKind.released.value


def test_current_positions_lists_newest_first(session, potato_and_market):
    commodity_id, _ = potato_and_market
    add_lot(
        session,
        commodity_id=commodity_id,
        quantity_kg=100.0,
        purchase_price_paise_per_kg=1000,
        purchase_date=date(2026, 11, 1),
    )
    second = add_lot(
        session,
        commodity_id=commodity_id,
        quantity_kg=200.0,
        purchase_price_paise_per_kg=1100,
        purchase_date=date(2026, 11, 2),
    )
    positions = current_positions(session)
    assert len(positions) == 2
    assert positions[0].lot.id == second.id  # newest lot first


def test_empty_book_has_no_positions(session):
    assert lot_count(session) == 0
    assert current_positions(session) == []
