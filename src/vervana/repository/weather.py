"""Weather observation store: append-only writes + latest-per-locality reads."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.models.weather import WeatherObservation
from vervana.time import now_utc
from vervana.weather.weatherunion import SOURCE_NAME, WeatherReading


def record_weather(
    session: Session,
    reading: WeatherReading,
    *,
    source_url: str,
    source: str = SOURCE_NAME,
    observed_at: datetime | None = None,
) -> int:
    """Append one reading. Returns the new row id. Append-only: never updates."""
    row = WeatherObservation(
        locality=reading.locality[:120],
        latitude=reading.lat,
        longitude=reading.lon,
        temperature_c=reading.temperature_c,
        humidity_pct=reading.humidity_pct,
        wind_speed=reading.wind_speed,
        wind_direction=reading.wind_direction,
        rain_intensity=reading.rain_intensity,
        rain_accumulation=reading.rain_accumulation,
        aqi_pm25=reading.aqi_pm25,
        aqi_pm10=reading.aqi_pm10,
        source=source,
        source_url=source_url,
        observed_at=observed_at or now_utc(),
    )
    session.add(row)
    session.flush()
    return row.id


def latest_per_locality(session: Session) -> list[WeatherObservation]:
    """The most recent stored reading for each locality (newest first)."""
    newest = (
        select(
            WeatherObservation.locality,
            func.max(WeatherObservation.observed_at).label("mx"),
        )
        .group_by(WeatherObservation.locality)
        .subquery()
    )
    stmt = (
        select(WeatherObservation)
        .join(
            newest,
            (WeatherObservation.locality == newest.c.locality)
            & (WeatherObservation.observed_at == newest.c.mx),
        )
        .order_by(WeatherObservation.observed_at.desc())
    )
    return list(session.execute(stmt).scalars())


def observation_count(session: Session) -> int:
    return int(session.execute(select(func.count(WeatherObservation.id))).scalar_one())
