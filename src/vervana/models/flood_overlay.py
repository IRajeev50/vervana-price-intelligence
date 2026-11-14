"""FloodOverlay: one zone's riverine flood tail-risk flag (append-only).

A RISK OVERLAY, not a price, not a forecast feature - its own table, never joined
into price_observation or used as a band input. Each row is one zone's worst
modelled riverine severity for a forecast window, traceable to its issue time and
source. Idempotent on (zone, issued_time). Labelled riverine-only; it is NOT
rainfall and NOT waterlogging.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class FloodOverlayRow(Base):
    __tablename__ = "flood_overlay"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(20))  # verified Severity enum value
    trend: Mapped[str] = mapped_column(String(20), default="")  # RISE|FALL|NO_CHANGE
    issued_time: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    valid_from: Mapped[date | None] = mapped_column(Date, default=None)
    valid_to: Mapped[date | None] = mapped_column(Date, default=None)

    source: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime)

    __table_args__ = (
        UniqueConstraint("zone", "issued_time", name="uq_flood_overlay_zone_issued"),
    )
