"""Context signals (Part 4.6): weather, diesel price, festival calendar.

These are MODEL FEATURES, not price observations, so they live in their own table and can
never be mistaken for a price. One row per (signal_type, region, date).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base


class ContextSignal(Base):
    __tablename__ = "context_signal"

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_type: Mapped[str] = mapped_column(String(40))  # weather | diesel | festival | ...
    region: Mapped[str] = mapped_column(String(80))
    on_date: Mapped[date] = mapped_column()
    value_numeric: Mapped[float | None] = mapped_column(Numeric(14, 4), default=None)
    value_text: Mapped[str | None] = mapped_column(String(200), default=None)
    source: Mapped[str] = mapped_column(String(120), default="manual")
    source_url: Mapped[str | None] = mapped_column(Text, default=None)
