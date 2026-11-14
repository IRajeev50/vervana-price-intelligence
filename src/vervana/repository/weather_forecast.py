"""Weather forecast store: idempotent upsert on (zone, run, valid_date) + reads."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.models.weather_forecast import WeatherForecast
from vervana.supply.weathernext import SOURCE, WEATHERNEXT_DOCS_URL, ForecastRecord
from vervana.time import now_utc


def record_forecasts(
    session: Session,
    records: list[ForecastRecord],
    *,
    source: str = SOURCE,
    source_url: str = WEATHERNEXT_DOCS_URL,
) -> dict[str, int]:
    """Append/refresh daily forecast rows. Idempotent on (zone, run, valid_date):
    a row already present for the same model run + valid date is updated in place,
    so re-pulling a run never duplicates. Returns {'added','updated'}."""
    added = updated = 0
    retrieved = now_utc()
    for r in records:
        existing = session.execute(
            select(WeatherForecast).where(
                WeatherForecast.zone == r.zone,
                WeatherForecast.model_run_time == r.model_run_time,
                WeatherForecast.valid_date == r.valid_date,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                WeatherForecast(
                    zone=r.zone,
                    model_run_time=r.model_run_time,
                    valid_date=r.valid_date,
                    lead_days=r.lead_days,
                    precip_mm_p10=r.precip_mm_p10,
                    precip_mm_p50=r.precip_mm_p50,
                    precip_mm_p90=r.precip_mm_p90,
                    tmax_c=r.tmax_c,
                    tmin_c=r.tmin_c,
                    source=source,
                    source_url=source_url,
                    retrieved_at=retrieved,
                )
            )
            added += 1
        else:
            existing.lead_days = r.lead_days
            existing.precip_mm_p10 = r.precip_mm_p10
            existing.precip_mm_p50 = r.precip_mm_p50
            existing.precip_mm_p90 = r.precip_mm_p90
            existing.tmax_c = r.tmax_c
            existing.tmin_c = r.tmin_c
            existing.retrieved_at = retrieved
            updated += 1
    session.flush()
    return {"added": added, "updated": updated}


def forecast_count(session: Session) -> int:
    return int(session.execute(select(func.count(WeatherForecast.id))).scalar_one())


def latest_run_for_zone(session: Session, zone: str) -> list[WeatherForecast]:
    """Every daily row of the most recent model run for one zone (by valid_date)."""
    run = session.execute(
        select(func.max(WeatherForecast.model_run_time)).where(WeatherForecast.zone == zone)
    ).scalar_one_or_none()
    if run is None:
        return []
    return list(
        session.execute(
            select(WeatherForecast)
            .where(WeatherForecast.zone == zone, WeatherForecast.model_run_time == run)
            .order_by(WeatherForecast.valid_date)
        ).scalars()
    )
