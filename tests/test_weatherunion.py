"""Offline mocked contract tests. Fixtures are test data, never live claims."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from vervana.config import Settings
from vervana.models.context import ContextSignal
from vervana.supply.scaffold import PartnerAccessPending
from vervana.supply.weatherunion import (
    WeatherSnapshot,
    WeatherUnionClient,
    WeatherUnionError,
    store_snapshot,
)


def payload(**overrides):
    return {
        "status": "200",
        "message": "",
        "device_type": 1,
        "locality_weather_data": {
            "temperature": 25,
            "humidity": 70,
            "rain_intensity": 0,
            "rain_accumulation": 2,
        },
        **overrides,
    }


def client(data=None, status=200):
    def handle(req):
        assert req.headers["X-Zomato-Api-Key"] == "test-only-not-real"
        assert req.url.params["latitude"] == "28.6"
        return httpx.Response(status, content=json.dumps(data if data is not None else payload()))

    return WeatherUnionClient(
        Settings(weatherunion_api_key="test-only-not-real"), transport=httpx.MockTransport(handle)
    )


def test_no_key_makes_no_request():
    c = WeatherUnionClient(Settings(weatherunion_api_key=None))
    assert "scaffold" in c.status().state
    with pytest.raises(PartnerAccessPending):
        c.fetch(latitude=28.6, longitude=77.2)


def test_key_is_masked_not_access_verified():
    c = client()
    assert "test-only-not-real" not in repr(c.settings)
    assert "not verified" in c.status().state


def test_success_missing_is_not_zero():
    s = client().fetch(latitude=28.6, longitude=77.2)
    assert s.values["wind_speed"] is None
    assert s.values["rain_intensity"] == 0
    assert "test-only" not in s.source_url
    assert s.fetched_at.tzinfo is not None


@pytest.mark.parametrize("status", [403, 429, 500, 302])
def test_fail_closed_http(status):
    with pytest.raises(WeatherUnionError, match=str(status)):
        client(status=status).fetch(latitude=28.6, longitude=77.2)


@pytest.mark.parametrize("message", ["temporarily unavailable", "latitude longitude not supported"])
def test_http_200_is_not_always_success(message):
    with pytest.raises(WeatherUnionError):
        client(payload(message=message)).fetch(latitude=28.6, longitude=77.2)


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"status": 403},
        payload(device_type=3),
        payload(locality_weather_data=None),
        payload(locality_weather_data={}),
        payload(locality_weather_data={"temperature": float("inf")}),
        payload(locality_weather_data={"humidity": 101}),
        payload(locality_weather_data={"temperature": True}),
        payload(locality_weather_data={"temperature": "25"}),
    ],
)
def test_bad_payloads(data):
    with pytest.raises(WeatherUnionError):
        client(data).fetch(latitude=28.6, longitude=77.2)


def test_rain_only_device_discards_nonrain_fields():
    s = client(payload(device_type=2)).fetch(latitude=28.6, longitude=77.2)
    assert s.values["temperature"] is None
    assert s.values["rain_accumulation"] == 2


@pytest.mark.parametrize("lat,lon", [(91, 0), (0, 181), (float("nan"), 0)])
def test_bad_coordinates(lat, lon):
    with pytest.raises(ValueError):
        client().fetch(latitude=lat, longitude=lon)


def test_network_error_redacted():
    def handle(req):
        raise httpx.ConnectError("potentially sensitive text", request=req)

    c = WeatherUnionClient(
        Settings(weatherunion_api_key="test-only-not-real"), transport=httpx.MockTransport(handle)
    )
    with pytest.raises(WeatherUnionError) as e:
        c.fetch(latitude=28.6, longitude=77.2)
    assert "sensitive" not in str(e.value)


def test_store_latest_idempotent_ist_date_and_nulls(session):
    s = WeatherSnapshot(
        datetime(2026, 10, 9, 20, tzinfo=UTC),
        1,
        "https://www.weatherunion.com/gw/weather/external/v0/get_weather_data",
        {"temperature": 25, "rain_accumulation": 2},
    )
    assert store_snapshot(session, s, region="Azadpur point") == 2
    assert store_snapshot(session, s, region="Azadpur point") == 2
    rows = list(session.scalars(select(ContextSignal)))
    assert len(rows) == 6
    assert all(r.on_date.isoformat() == "2026-10-10" for r in rows)
    newer = WeatherSnapshot(
        s.fetched_at + timedelta(minutes=10), 2, s.source_url, {"rain_accumulation": 3}
    )
    store_snapshot(session, newer, region="Azadpur point")
    temp = session.scalar(
        select(ContextSignal).where(ContextSignal.signal_type == "wu_temperature_c")
    )
    assert temp.value_numeric is None
    assert "station_time=unknown" in temp.value_text
    with pytest.raises(ValueError, match="Older receipt"):
        store_snapshot(session, s, region="Azadpur point")


def test_storage_rejects_naive_receipt_and_empty_site(session):
    s = WeatherSnapshot(datetime(2026, 10, 9), 1, "test", {"temperature": 20})
    with pytest.raises(ValueError):
        store_snapshot(session, s, region="site")
    with pytest.raises(ValueError):
        store_snapshot(session, s, region="")


def test_cli_reports_scaffold_and_missing_key(monkeypatch):
    from typer.testing import CliRunner

    from vervana.cli import app

    monkeypatch.delenv("VERVANA_WEATHERUNION_API_KEY", raising=False)
    runner = CliRunner()
    status = runner.invoke(app, ["supply", "weatherunion-status"])
    assert status.exit_code == 0
    assert "SCAFFOLD" in status.stdout
    result = runner.invoke(app, ["supply", "weatherunion-fetch", "28.6", "77.2", "site"])
    assert result.exit_code == 1
    assert "key pending" in result.output


def test_invalid_json_is_safe():
    c = WeatherUnionClient(
        Settings(weatherunion_api_key="test-only-not-real"),
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"not-json")),
    )
    with pytest.raises(WeatherUnionError, match="Malformed"):
        c.fetch(latitude=28.6, longitude=77.2)
