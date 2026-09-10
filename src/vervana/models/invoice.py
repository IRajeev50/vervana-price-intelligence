"""Trader invoices — the GROUND TRUTH reference for M5 (§5.2).

Per R4, Agmarknet is NOT ground truth (DMI disclaims it; markets go unreported). The
reference for validation is real executed trader invoices. This table holds them; it is
empty until the founder supplies invoices, at which point the ground-truth study upgrades
from an interim comparator-vs-comparator check to a real verdict — no code change needed.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base


class Invoice(Base):
    __tablename__ = "invoice"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodity.id"))
    market_id: Mapped[int | None] = mapped_column(ForeignKey("market.id"), default=None)
    invoice_date: Mapped[date] = mapped_column()
    # The executed price actually paid, normalised to ₹/kg (integer paise). This is the
    # reference every other source is measured against.
    price_paise_per_kg: Mapped[int] = mapped_column(BigInteger)
    trader: Mapped[str | None] = mapped_column(String(160), default=None)
    source_ref: Mapped[str | None] = mapped_column(
        String(300), default=None
    )  # invoice no./photo id
    notes: Mapped[str | None] = mapped_column(Text, default=None)
