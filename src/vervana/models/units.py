"""Bag-weight / unit-conversion lookup (Part 3.3).

Bag weights vary by mandi, by commodity, and over time. NEVER hardcode 50 kg. When
no row matches an observation's (market, commodity, unit_raw), the canonical ₹/kg
price stays NULL and the raw unit is preserved — we do not guess a weight.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base


class UnitConvention(Base):
    __tablename__ = "unit_convention"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Either/both may be NULL to express commodity-wide or market-wide conventions;
    # the repository prefers the most specific matching row.
    market_id: Mapped[int | None] = mapped_column(ForeignKey("market.id"), default=None)
    commodity_id: Mapped[int | None] = mapped_column(ForeignKey("commodity.id"), default=None)

    unit_raw: Mapped[str] = mapped_column(String(64))
    kg_equivalent: Mapped[float] = mapped_column(Numeric(12, 4))  # Numeric, never float column
    source: Mapped[str] = mapped_column(String(120))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)

    effective_from: Mapped[date | None] = mapped_column(default=None)
    effective_to: Mapped[date | None] = mapped_column(default=None)

    __table_args__ = (Index("ix_unitconv_lookup", "commodity_id", "market_id", "unit_raw"),)
