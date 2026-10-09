"""WeatherUnion get_weather_data: fetch + parse one locality's current weather.

The response parser (`parse_weather_response`) is PURE - it turns the API's JSON
into a `WeatherReading` and is unit-tested without a network. `fetch_reading`
is the thin httpx wrapper (header auth) around it.

Honest guardrails, same creed as every other feed here:
  * No API key -> `WeatherUnionError`, never a silent empty reading.
  * The API answers with a `status`/`message`; anything other than a success
    payload with a `locality_weather_data` object raises - we store nothing
    rather than invent a zero.
  * The API returns a real-time snapshot with NO timestamp of its own, so the
    caller stamps capture time (UTC) as the observation instant and says so -
    we never imply a precision the source does not give.
  * A field the station did not report comes back as None, not 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from vervana.config import Settings, get_settings

SOURCE_NAME = "WeatherUnion (Zomato) hyperlocal station"
# Header name per the public API. Casing is not significant to httpx/HTTP, but we
# send the documented capitalisation.
API_KEY_HEADER = "X-Zomato-Api-Key"


class WeatherUnionError(RuntimeError):
    """Raised when WeatherUnion cannot give a usable reading (no key, HTTP error,
    non-success status, or a missing locality_weather_data object)."""


@dataclass(frozen=True)
class WeatherReading:
    """One station's current weather. Any field the station did not report is None
    (never 0). Values are passed through from the API unit-for-unit:
    temperature °C, humidity %, wind m/s, wind direction degrees, rain mm."""

    locality: str
    lat: float
    lon: float
    temperature_c: float | None
    humidity_pct: float | None
    wind_speed: float | None
    wind_direction: float | None
    rain_intensity: float | None
    rain_accumulation: float | None
    aqi_pm25: float | None
    aqi_pm10: float | None


def _num(value: object) -> float | None:
    """Coerce an API scalar to float, or None. WeatherUnion uses sentinels like
    -999 / "null" for "no reading"; those become None so a gap is never a value."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # -999 (and similar large negatives) is the documented "no data" sentinel.
    if f <= -999.0:
        return None
    return f


def parse_weather_response(
    payload: dict, *, locality: str, lat: float, lon: float
) -> WeatherReading:
    """Turn a get_weather_data JSON body into a WeatherReading. Pure.

    Raises WeatherUnionError when the payload is not a usable success response
    (so the caller stores nothing rather than a fabricated reading).
    """
    if not isinstance(payload, dict):
        raise WeatherUnionError("weather response was not a JSON object")

    status = str(payload.get("status", "")).lower()
    message = str(payload.get("message", "")).strip()
    data = payload.get("locality_weather_data")

    # A success body carries a locality_weather_data object. Anything else - an
    # error status, a textual message, a missing/empty data block - is surfaced,
    # never smoothed into zeros.
    if not isinstance(data, dict) or not data:
        raise WeatherUnionError(
            f"no weather data for '{locality}'"
            + (f": {message}" if message else f" (status={status or 'unknown'})")
        )
    if status and status not in {"success", "ok", "200"}:
        raise WeatherUnionError(
            f"weather status '{status}' for '{locality}'" + (f": {message}" if message else "")
        )

    return WeatherReading(
        locality=locality,
        lat=lat,
        lon=lon,
        temperature_c=_num(data.get("temperature")),
        humidity_pct=_num(data.get("humidity")),
        wind_speed=_num(data.get("wind_speed")),
        wind_direction=_num(data.get("wind_direction")),
        rain_intensity=_num(data.get("rain_intensity")),
        rain_accumulation=_num(data.get("rain_accumulation")),
        aqi_pm25=_num(data.get("aqi_pm_2_point_5")),
        aqi_pm10=_num(data.get("aqi_pm_10")),
    )


def fetch_reading(
    *,
    lat: float,
    lon: float,
    locality: str = "",
    settings: Settings | None = None,
) -> WeatherReading:
    """Fetch one locality's current weather from WeatherUnion. Thin IO wrapper.

    Raises WeatherUnionError if the API key is not configured, the request fails,
    or the body is not a usable success response.
    """
    import httpx

    settings = settings or get_settings()
    api_key = settings.weather_union_api_key
    if not api_key:
        raise WeatherUnionError(
            "WEATHER_UNION_API_KEY not configured - set VERVANA_WEATHER_UNION_API_KEY "
            "in .env (free key from the WeatherUnion dashboard). Storing nothing."
        )
    try:
        resp = httpx.get(
            settings.weather_union_url,
            params={"latitude": lat, "longitude": lon},
            headers={API_KEY_HEADER: api_key},
            timeout=settings.weather_union_timeout_seconds,
        )
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        raise WeatherUnionError(f"WeatherUnion request failed for '{locality}': {exc}") from None
    except ValueError as exc:  # non-JSON body
        raise WeatherUnionError(
            f"WeatherUnion returned a non-JSON body for '{locality}': {exc}"
        ) from None
    return parse_weather_response(payload, locality=locality, lat=lat, lon=lon)
