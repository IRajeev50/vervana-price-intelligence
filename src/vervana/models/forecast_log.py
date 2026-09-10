"""Prospective forecast log (§5.3): tomorrow's call, posted today, scored daily.

Per the research this is the only forecasting evidence a buyer will believe, and the only
moat that compounds for free. Forecasts are append-only and published unedited; scoring
fills in the actual once the target day's price is known.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class ProspectiveForecast(Base):
    __tablename__ = "prospective_forecast"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodity.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("market.id"))
    target_date: Mapped[date] = mapped_column()
    made_at: Mapped[datetime] = mapped_column(UTCDateTime)
    model: Mapped[str] = mapped_column(String(40))

    point_paise: Mapped[int] = mapped_column(BigInteger)
    low_paise: Mapped[int] = mapped_column(BigInteger)
    high_paise: Mapped[int] = mapped_column(BigInteger)

    # Filled by scoring once the target day's actual price is known. Append-only otherwise.
    actual_paise: Mapped[int | None] = mapped_column(BigInteger, default=None)
    abs_error_paise: Mapped[int | None] = mapped_column(BigInteger, default=None)
    hit_interval: Mapped[bool | None] = mapped_column(default=None)
