"""Inventory store for The Book (M17): lots + append-only event log.

The lot row holds immutable purchase facts; status lives entirely in the append-only
`lot_event` log, so a position's history is auditable and the lot is never rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.models.inventory import InventoryLot, LotEvent, LotEventKind
from vervana.time import now_utc


def add_lot(
    session: Session,
    *,
    commodity_id: int,
    quantity_kg: float,
    purchase_price_paise_per_kg: int,
    purchase_date: date,
    warehouse: str = "",
    warehouse_lat: float | None = None,
    warehouse_lon: float | None = None,
    intended_market_id: int | None = None,
    variety: str | None = None,
    grade: str | None = None,
    source_ref: str | None = None,
    notes: str | None = None,
) -> InventoryLot:
    """Record a lot and its opening ACQUIRED event in one step."""
    lot = InventoryLot(
        commodity_id=commodity_id,
        variety=variety,
        grade=grade,
        quantity_kg=quantity_kg,
        purchase_price_paise_per_kg=purchase_price_paise_per_kg,
        purchase_date=purchase_date,
        warehouse=warehouse,
        warehouse_lat=warehouse_lat,
        warehouse_lon=warehouse_lon,
        intended_market_id=intended_market_id,
        source_ref=source_ref,
        notes=notes,
        created_at=now_utc(),
    )
    session.add(lot)
    session.flush()
    append_event(
        session,
        lot.id,
        LotEventKind.acquired,
        quantity_kg=quantity_kg,
        price_paise_per_kg=purchase_price_paise_per_kg,
        event_date=purchase_date,
        note="opening acquisition",
    )
    return lot


def append_event(
    session: Session,
    lot_id: int,
    kind: LotEventKind,
    *,
    event_date: date,
    quantity_kg: float | None = None,
    price_paise_per_kg: int | None = None,
    note: str | None = None,
) -> LotEvent:
    ev = LotEvent(
        lot_id=lot_id,
        kind=kind,
        quantity_kg=quantity_kg,
        price_paise_per_kg=price_paise_per_kg,
        event_date=event_date,
        note=note,
        created_at=now_utc(),
    )
    session.add(ev)
    session.flush()
    return ev


def latest_event(session: Session, lot_id: int) -> LotEvent | None:
    return session.execute(
        select(LotEvent)
        .where(LotEvent.lot_id == lot_id)
        .order_by(LotEvent.event_date.desc(), LotEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_lot(session: Session, lot_id: int) -> InventoryLot | None:
    return session.get(InventoryLot, lot_id)


def lot_count(session: Session) -> int:
    return int(session.execute(select(func.count(InventoryLot.id))).scalar_one())


@dataclass(frozen=True)
class Position:
    """A lot's current standing, derived from the event log (never a stored status)."""

    lot: InventoryLot
    status: str  # latest event kind value
    released_kg: float
    remaining_kg: float


def _released_kg(session: Session, lot_id: int) -> float:
    total = session.execute(
        select(func.coalesce(func.sum(LotEvent.quantity_kg), 0.0)).where(
            LotEvent.lot_id == lot_id, LotEvent.kind == LotEventKind.released
        )
    ).scalar_one()
    return float(total or 0.0)


def position_for(session: Session, lot_id: int) -> Position | None:
    lot = get_lot(session, lot_id)
    if lot is None:
        return None
    latest = latest_event(session, lot_id)
    released = _released_kg(session, lot_id)
    remaining = max(float(lot.quantity_kg) - released, 0.0)
    status = latest.kind.value if latest else LotEventKind.acquired.value
    return Position(lot=lot, status=status, released_kg=released, remaining_kg=remaining)


def current_positions(session: Session) -> list[Position]:
    """Every lot with its derived status and remaining quantity, newest lot first."""
    lots = session.scalars(select(InventoryLot).order_by(InventoryLot.id.desc())).all()
    out: list[Position] = []
    for lot in lots:
        pos = position_for(session, lot.id)
        if pos is not None:
            out.append(pos)
    return out
