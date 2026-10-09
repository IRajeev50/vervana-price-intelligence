"""Weather Union current-weather seam. Never a forecast or historical weather feed."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.config import Settings, get_settings
from vervana.models.context import ContextSignal
from vervana.supply.scaffold import FeedStatus, PartnerAccessPending
from vervana.time import now_utc, to_ist, to_utc

BASE_URL = "https://www.weatherunion.com/gw/weather/external/v0"
DOCS_URL = "https://www.weatherunion.com/dashboard/#tag/default/GET/get_weather_data"
# Names include units so mm/min cannot accidentally become daily rainfall deficit.
FIELDS = {
    "temperature": ("wu_temperature_c", -100, 100),
    "humidity": ("wu_humidity_pct", 0, 100),
    "wind_speed": ("wu_wind_speed_mps", 0, None),
    "wind_direction": ("wu_wind_direction_deg", 0, 360),
    "rain_intensity": ("wu_rain_intensity_mm_min", 0, None),
    "rain_accumulation": ("wu_rain_today_mm", 0, None),
}


class WeatherUnionError(RuntimeError):
    """Safe error: never includes credentials, request headers, or response bodies."""


@dataclass(frozen=True)
class WeatherSnapshot:
    fetched_at: datetime  # receipt time, NOT a station observation timestamp
    device_type: int
    source_url: str
    values: dict[str, float | None]


class WeatherUnionClient:
    def __init__(self, settings: Settings | None = None, *, transport=None):
        self.settings = settings or get_settings()
        self.transport = transport

    def status(self) -> FeedStatus:
        configured = bool(self.settings.weatherunion_api_key)
        return FeedStatus(
            name="weatherunion",
            title="Weather Union current local weather",
            layer="scaffold",
            configured=configured,
            state=(
                "configured - access/coverage not verified"
                if configured
                else "scaffold - API key pending"
            ),
            emits=", ".join(v[0] for v in FIELDS.values()),
            hint="set VERVANA_WEATHERUNION_API_KEY; run supply weatherunion-fetch",
            docs_url=DOCS_URL,
        )

    def fetch(self, *, latitude: float, longitude: float) -> WeatherSnapshot:
        if not (
            math.isfinite(latitude)
            and -90 <= latitude <= 90
            and math.isfinite(longitude)
            and -180 <= longitude <= 180
        ):
            raise ValueError("Invalid latitude/longitude")
        key = self.settings.weatherunion_api_key
        if not key:
            raise PartnerAccessPending("Weather Union scaffold: API key pending; no request made")
        # One bounded call, no automatic retries on quota exhaustion/auth failures.
        try:
            with httpx.Client(
                timeout=15, transport=self.transport, follow_redirects=False
            ) as client:
                response = client.get(
                    BASE_URL + "/get_weather_data",
                    params={"latitude": latitude, "longitude": longitude},
                    headers={"X-Zomato-Api-Key": key.get_secret_value()},
                )
        except httpx.HTTPError:
            raise WeatherUnionError("Weather Union request failed; no data ingested") from None
        if response.status_code != 200:
            raise WeatherUnionError(f"Weather Union HTTP {response.status_code}; no data ingested")
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            if str(payload.get("status")) != "200" or payload.get("message"):
                raise WeatherUnionError("Weather Union unavailable/unsupported; no data ingested")
            device = payload.get("device_type")
            if isinstance(device, bool) or device not in (1, 2):
                raise ValueError
            raw = payload["locality_weather_data"]
            if not isinstance(raw, dict):
                raise ValueError
            values = {}
            for field, (_, lower, upper) in FIELDS.items():
                value = raw.get(field)
                # Rain-only stations cannot emit temperature/humidity/wind observations.
                if device == 2 and field not in ("rain_intensity", "rain_accumulation"):
                    value = None
                if value is not None:
                    if isinstance(value, bool) or not isinstance(value, (float, int)):
                        raise ValueError
                    value = float(value)
                    if (
                        not math.isfinite(value)
                        or value < lower
                        or (upper is not None and value > upper)
                    ):
                        raise ValueError
                values[field] = value
        except (ValueError, TypeError, KeyError):
            raise WeatherUnionError("Malformed Weather Union response; no data ingested") from None
        if all(v is None for v in values.values()):
            raise WeatherUnionError("Weather Union returned no measurements; no data ingested")
        return WeatherSnapshot(now_utc(), device, str(response.url), values)


def store_snapshot(session: Session, snapshot: WeatherSnapshot, *, region: str) -> int:
    """Daily latest-received snapshot, not an average, max, forecast or historical backfill.

    Null remains missing. A newer receipt clears a formerly available metric to prevent
    stale values masquerading as current ones. Caller owns commit/rollback.
    """
    if not region.strip() or len(region) > 80:
        raise ValueError("region must be a non-empty site-specific label up to 80 characters")
    stamp = to_utc(snapshot.fetched_at).isoformat()
    day = to_ist(snapshot.fetched_at).date()
    metadata = f"received_at={stamp};device={snapshot.device_type};station_time=unknown"
    for field, (kind, _, _) in FIELDS.items():
        rows = list(
            session.scalars(
                select(ContextSignal).where(
                    ContextSignal.signal_type == kind,
                    ContextSignal.region == region,
                    ContextSignal.on_date == day,
                    ContextSignal.source == "weatherunion",
                )
            )
        )
        for existing in rows:
            previous = (existing.value_text or "").split(";", 1)[0]
            if previous.startswith("received_at="):
                if (
                    datetime.fromisoformat(previous.removeprefix("received_at="))
                    > snapshot.fetched_at
                ):
                    raise ValueError("Older receipt cannot overwrite a newer daily snapshot")
        row = (
            rows[0]
            if rows
            else ContextSignal(
                signal_type=kind,
                region=region,
                on_date=day,
                source="weatherunion",
            )
        )
        for duplicate in rows[1:]:
            session.delete(duplicate)
        row.value_numeric = snapshot.values.get(field)
        row.value_text = metadata
        row.source_url = snapshot.source_url
        session.add(row)
    session.flush()
    return sum(v is not None for v in snapshot.values.values())
