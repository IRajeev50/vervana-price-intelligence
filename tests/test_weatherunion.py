"""WeatherUnion parser: pure response -> WeatherReading, no network.

Guards: a success body is mapped field-for-field; the "no data" sentinel (-999)
and missing fields become None (never 0); an error/empty payload raises rather
than fabricating a reading; and the Delhi locality CSV loads with real floats.
"""

from __future__ import annotations

import pytest

from vervana.weather.localities import load_localities
from vervana.weather.weatherunion import (
    WeatherUnionError,
    parse_weather_response,
)

_OK = {
    "status": "success",
    "message": "",
    "device_type": 1,
    "locality_weather_data": {
        "temperature": 29.4,
        "humidity": 71.0,
        "wind_speed": 3.2,
        "wind_direction": 180.0,
        "rain_intensity": 0.0,
        "rain_accumulation": 12.5,
        "aqi_pm_2_point_5": 143.0,
        "aqi_pm_10": 210.0,
    },
}


def test_parse_success_maps_every_field():
    r = parse_weather_response(_OK, locality="Azadpur Mandi", lat=28.7126, lon=77.1764)
    assert r.locality == "Azadpur Mandi"
    assert (r.lat, r.lon) == (28.7126, 77.1764)
    assert r.temperature_c == 29.4
    assert r.humidity_pct == 71.0
    assert r.wind_speed == 3.2
    assert r.wind_direction == 180.0
    assert r.rain_intensity == 0.0
    assert r.rain_accumulation == 12.5
    assert r.aqi_pm25 == 143.0
    assert r.aqi_pm10 == 210.0


def test_sentinel_and_missing_fields_become_none_not_zero():
    payload = {
        "status": "success",
        "locality_weather_data": {
            "temperature": 30.0,
            "humidity": -999.0,  # documented "no reading" sentinel
            "rain_accumulation": None,
            # wind + aqi fields absent entirely
        },
    }
    r = parse_weather_response(payload, locality="Okhla Mandi", lat=28.5, lon=77.2)
    assert r.temperature_c == 30.0
    assert r.humidity_pct is None  # sentinel -> None, not -999 and not 0
    assert r.rain_accumulation is None
    assert r.wind_speed is None
    assert r.aqi_pm25 is None


def test_error_and_empty_payloads_raise():
    # No locality_weather_data block -> raise (store nothing).
    with pytest.raises(WeatherUnionError):
        parse_weather_response(
            {"status": "failure", "message": "locality temporarily unavailable"},
            locality="Ghazipur Mandi",
            lat=28.6,
            lon=77.3,
        )
    # Present key but empty object -> raise.
    with pytest.raises(WeatherUnionError):
        parse_weather_response(
            {"status": "success", "locality_weather_data": {}},
            locality="Ghazipur Mandi",
            lat=28.6,
            lon=77.3,
        )
    # Non-success status even with data -> raise.
    with pytest.raises(WeatherUnionError):
        parse_weather_response(
            {"status": "error", "locality_weather_data": {"temperature": 1.0}},
            locality="x",
            lat=1.0,
            lon=1.0,
        )


def test_localities_csv_loads_with_real_coordinates():
    locs = load_localities()
    assert locs, "expected seeded Delhi mandi localities"
    by = {x.name: x for x in locs}
    assert "Azadpur Mandi" in by
    az = by["Azadpur Mandi"]
    assert 28.0 < az.lat < 29.0 and 76.0 < az.lon < 78.0
    assert az.state == "Delhi"
