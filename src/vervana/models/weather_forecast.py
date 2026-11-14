"""WeatherForecast: one daily WeatherNext 3 forecast row per zone per valid date.

A FORECAST, not a price and not a chain signal - it lives in its own table and is
never joined into price_observation. Append-only; each row is traceable to its
model run and source. Idempotent on (zone, model_run_time, valid_date) so a
re-pull of the same run updates nothing and duplicates nothing.

Precip percentiles are the daily SUM of the hourly percentile values (see
`supply/weathernext.py` for the temporal-independence caveat): a usable band, not
an exact daily quantile. tmax/tmin are the day's max/min 2m temperature, NULL when
no hour reported one (never 0).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class WeatherForecast(Base):
    __tablename__ = "weather_forecast"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone: Mapped[str] = mapped_column(String(60), index=True)
    model_run_time: Mapped[datetime] = mapped_column(UTCDateTime)
    valid_date: Mapped[date] = mapped_column(Date, index=True)
    lead_days: Mapped[int] = mapped_column(Integer)

    precip_mm_p10: Mapped[float | None] = mapped_column(Float, default=None)
    precip_mm_p50: Mapped[float | None] = mapped_column(Float, default=None)
    precip_mm_p90: Mapped[float | None] = mapped_column(Float, default=None)
    tmax_c: Mapped[float | None] = mapped_column(Float, default=None)
    tmin_c: Mapped[float | None] = mapped_column(Float, default=None)

    # Provenance is mandatory.
    source: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime)

    __table_args__ = (
        UniqueConstraint(
            "zone", "model_run_time", "valid_date", name="uq_weather_forecast_run_valid"
        ),
    )
