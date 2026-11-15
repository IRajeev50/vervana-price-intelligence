"""Inventory lots — "The Book" (M17), the commercial decision layer's physical base.

An `InventoryLot` is the IMMUTABLE purchase facts of one physical lot sitting in a
warehouse: what was bought, how much, at what price, when, aimed at which market. The
lot row is never rewritten. A lot's life (held, partially/fully released, written off)
is an APPEND-ONLY `LotEvent` log, so the current position is the latest event and the
whole history is auditable — matching the project's append-only, provenance-first ethos.

Money is integer paise (never float). Both tables are EMPTY until the operator enters
real lots — like `invoice`, inventory is never seeded with fabricated stock.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime, enum_column


class LotEventKind(enum.StrEnum):
    """The lifecycle of a lot. ACQUIRED is written once with the lot; the rest append."""

    acquired = "ACQUIRED"
    held = "HELD"
    released = "RELEASED"
    written_off = "WRITTEN_OFF"


class InventoryLot(Base):
    """Immutable purchase facts of one physical lot. Never rewritten."""

    __tablename__ = "inventory_lot"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodity.id"), index=True)
    variety: Mapped[str | None] = mapped_column(String(80), default=None)
    grade: Mapped[str | None] = mapped_column(String(80), default=None)

    quantity_kg: Mapped[float] = mapped_column(Numeric(14, 3))
    # The price actually paid, normalised to ₹/kg (integer paise). Exact, never float money.
    purchase_price_paise_per_kg: Mapped[int] = mapped_column(BigInteger)
    purchase_date: Mapped[date] = mapped_column(Date)

    # Warehouse is a label; coordinates are optional and only used to estimate outbound
    # freight (reusing the geo distance helper). Missing coords -> "distance unknown",
    # never a guessed logistics cost.
    warehouse: Mapped[str] = mapped_column(String(160), default="")
    warehouse_lat: Mapped[float | None] = mapped_column(Float, default=None)
    warehouse_lon: Mapped[float | None] = mapped_column(Float, default=None)

    # The destination this lot is aimed at (for the REROUTE comparison). Optional.
    intended_market_id: Mapped[int | None] = mapped_column(
        ForeignKey("market.id"), default=None
    )

    source_ref: Mapped[str | None] = mapped_column(String(300), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class LotEvent(Base):
    """Append-only status event for a lot. Current status = the latest event."""

    __tablename__ = "lot_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("inventory_lot.id"), index=True)
    kind: Mapped[LotEventKind] = mapped_column(enum_column(LotEventKind))

    # Optional because only a RELEASED event carries a realised quantity/price; a HELD or
    # WRITTEN_OFF event may carry neither.
    quantity_kg: Mapped[float | None] = mapped_column(Numeric(14, 3), default=None)
    price_paise_per_kg: Mapped[int | None] = mapped_column(BigInteger, default=None)
    event_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
