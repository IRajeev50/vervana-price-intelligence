"""Quick-commerce retail detail (Part 4.5).

A retail offer's pack economics are kept SEPARATELY from the canonical ₹/kg, so the
pack size, MRP, selling price and fees are never lost when we normalise to ₹/kg. One
row per price_observation of source_class = retail_offer.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base


class RetailOfferDetail(Base):
    __tablename__ = "retail_offer_detail"

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("price_observation.id"))
    platform: Mapped[str] = mapped_column(String(40))  # Blinkit / Zepto / Instamart / ...
    sku_title: Mapped[str] = mapped_column(String(300))
    pack_size_raw: Mapped[str] = mapped_column(String(64))  # e.g. "500 g", "1 kg"
    pack_kg: Mapped[float] = mapped_column(Numeric(12, 4))
    mrp_paise: Mapped[int | None] = mapped_column(BigInteger, default=None)
    selling_price_paise: Mapped[int] = mapped_column(BigInteger)
    fees_paise: Mapped[int | None] = mapped_column(BigInteger, default=None)
