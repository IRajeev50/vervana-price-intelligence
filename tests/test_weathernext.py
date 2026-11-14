"""WeatherNext 3 seam: pure daily aggregation + honest access-pending scaffold.

No network. The aggregation is model-independent and fully tested here; the live
BigQuery pull stays inert (raises) until allowlist access + credentials exist, and
is proven to fetch nothing / store nothing while pending.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from vervana.config import Settings
from vervana.supply.feeds import collect_feed_status
from vervana.supply.scaffold import PartnerAccessPending
from vervana.supply.weathernext import (
    ForecastPoint,
    WeatherNextClient,
    aggregate_daily,
)

_RUN = datetime(2026, 11, 14, 0, 0, tzinfo=UTC)


def _pt(zone: str, day: int, hour: int, p10: float, p50: float, p90: float, t: float | None):
    return ForecastPoint(
        zone=zone,
        model_run_time=_RUN,
        valid_time=datetime(2026, 11, day, hour, tzinfo=UTC),
        precip_mm_p10=p10,
        precip_mm_p50=p50,
        precip_mm_p90=p90,
        temp_c=t,
    )


def test_aggregate_daily_sums_precip_and_minmax_temp():
    pts = [
        _pt("nashik-onion", 15, 0, 0.0, 0.5, 1.0, 20.0),
        _pt("nashik-onion", 15, 1, 0.1, 0.5, 2.0, 24.0),
        _pt("nashik-onion", 16, 0, 0.0, 0.0, 0.0, 18.0),  # next day
        _pt("kinnaur-apple", 15, 0, 1.0, 2.0, 3.0, None),  # no temp reported this hour
    ]
    recs = {(r.zone, r.valid_date): r for r in aggregate_daily(pts)}

    d15 = recs[("nashik-onion", date(2026, 11, 15))]
    assert d15.precip_mm_p10 == 0.1  # 0.0 + 0.1
    assert d15.precip_mm_p50 == 1.0  # 0.5 + 0.5
    assert d15.precip_mm_p90 == 3.0  # 1.0 + 2.0
    assert d15.tmax_c == 24.0 and d15.tmin_c == 20.0
    assert d15.lead_days == 1  # valid 15th, run 14th

    d16 = recs[("nashik-onion", date(2026, 11, 16))]
    assert d16.lead_days == 2

    # A zone whose only hour had no temperature yields NULL tmax/tmin, never 0.
    k = recs[("kinnaur-apple", date(2026, 11, 15))]
    assert k.tmax_c is None and k.tmin_c is None
    assert k.precip_mm_p90 == 3.0


def test_aggregate_daily_is_sorted_and_empty_safe():
    assert aggregate_daily([]) == []
    recs = aggregate_daily(
        [_pt("z-b", 16, 0, 0, 0, 0, 1.0), _pt("z-a", 15, 0, 0, 0, 0, 1.0)]
    )
    assert [(r.zone, r.valid_date) for r in recs] == [
        ("z-a", date(2026, 11, 15)),
        ("z-b", date(2026, 11, 16)),
    ]


def _unset_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k in (
        "VERVANA_WEATHERNEXT_GCP_PROJECT",
        "VERVANA_WEATHERNEXT_BQ_DATASET",
        "VERVANA_WEATHERNEXT_BQ_TABLE",
        "VERVANA_WEATHERNEXT_CREDENTIALS_PATH",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(k, raising=False)
    return Settings()


def test_scaffold_reports_access_pending_and_fetches_nothing(monkeypatch: pytest.MonkeyPatch):
    client = WeatherNextClient(_unset_settings(monkeypatch))
    s = client.status()
    assert s.layer == "scaffold"
    assert "access pending" in s.state
    assert client.configured() is False
    # Fetching raises - and makes no request, invents no row.
    with pytest.raises(PartnerAccessPending):
        client.fetch_forecasts([])


def test_feed_registry_lists_weathernext_as_scaffold(monkeypatch: pytest.MonkeyPatch):
    feeds = {f.name: f for f in collect_feed_status(_unset_settings(monkeypatch))}
    assert "google-weathernext" in feeds
    assert feeds["google-weathernext"].layer == "scaffold"
    assert "weather_forecast" in feeds["google-weathernext"].emits


def test_record_forecasts_is_idempotent_on_run_and_valid_date(session):
    from vervana.repository.weather_forecast import (
        forecast_count,
        latest_run_for_zone,
        record_forecasts,
    )
    from vervana.supply.weathernext import ForecastRecord

    recs = aggregate_daily(
        [_pt("nashik-onion", 15, 0, 0.0, 0.5, 1.0, 20.0), _pt("nashik-onion", 16, 0, 0, 0, 0, 18.0)]
    )
    assert record_forecasts(session, recs) == {"added": 2, "updated": 0}
    assert forecast_count(session) == 2

    # Re-pulling the SAME run updates in place, never duplicates.
    revised = [
        ForecastRecord(
            zone=recs[0].zone,
            model_run_time=recs[0].model_run_time,
            valid_date=recs[0].valid_date,
            lead_days=recs[0].lead_days,
            precip_mm_p10=9.9,
            precip_mm_p50=9.9,
            precip_mm_p90=9.9,
            tmax_c=30.0,
            tmin_c=10.0,
        )
    ]
    assert record_forecasts(session, revised) == {"added": 0, "updated": 1}
    assert forecast_count(session) == 2  # still 2, not 3

    rows = latest_run_for_zone(session, "nashik-onion")
    assert [r.valid_date for r in rows] == sorted(r.valid_date for r in rows)
    assert rows[0].precip_mm_p50 == 9.9  # the update landed
