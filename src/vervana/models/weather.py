"""WeatherObservation: one captured WeatherUnion reading (append-only).

A WEATHER fact, not a price - it lives in its own table and is never joined into
price_observation. Each row is one locality snapshot at capture time, with
provenance (source + source_url) mandatory, exactly like every other observation
this platform stores.

`observed_at` is CAPTURE time (UTC): the get_weather_data response carries no
timestamp of its own, so we record when we polled and never imply the station
reported at a different instant. Any measurement the station did not report is
NULL (never 0), so a gap is distinguishable from a real zero.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class WeatherObservation(Base):
    __tablename__ = "weather_observation"

    id: Mapped[int] = mapped_column(primary_key=True)
    locality: Mapped[str] = mapped_column(String(120), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)

    # Measurements - nullable, because a station may not report every one.
    temperature_c: Mapped[float | None] = mapped_column(Float, default=None)
    humidity_pct: Mapped[float | None] = mapped_column(Float, default=None)
    wind_speed: Mapped[float | None] = mapped_column(Float, default=None)
    wind_direction: Mapped[float | None] = mapped_column(Float, default=None)
    rain_intensity: Mapped[float | None] = mapped_column(Float, default=None)
    rain_accumulation: Mapped[float | None] = mapped_column(Float, default=None)
    aqi_pm25: Mapped[float | None] = mapped_column(Float, default=None)
    aqi_pm10: Mapped[float | None] = mapped_column(Float, default=None)

    # Provenance is mandatory.
    source: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))
    # Capture time (UTC). The API gives no timestamp; see module docstring.
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
