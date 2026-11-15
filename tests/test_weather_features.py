"""M20a: belt→mandi weather link (W3) + the dormant weather-feature builder (W4).

Offline. The builder reduces a series' linked belts' latest forecast run to a supply-stress
feature, returning None when there is no link or no stored forecast (access pending) — never
a fabricated zero. It is NOT on the live band; these tests pin the seam, not a forecast.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from vervana.forecast.weather_features import weather_feature_for_series
from vervana.models.weather_forecast import WeatherForecast
from vervana.supply.zones import zones_for_series

# --- W3 belt→mandi link ----------------------------------------------------

def test_zones_for_series_links_belt_to_its_mandi():
    z = zones_for_series("Onion", "Lasalgaon")
    assert [x.zone for x in z] == ["nashik-onion"]
    assert zones_for_series("Capsicum", "PMY Kullu")[0].zone == "kullu-capsicum"
    # A real mandi but not linked to that commodity's belt -> no match (honest empty).
    assert zones_for_series("Onion", "Azadpur") == []
    assert zones_for_series("", "Lasalgaon") == []


def _forecast(zone, valid, precip_p50, tmax):
    run = datetime(2026, 11, 14, 0, 0, tzinfo=UTC)
    return WeatherForecast(
        zone=zone,
        model_run_time=run,
        valid_date=valid,
        lead_days=(valid - run.date()).days,
        precip_mm_p10=precip_p50 / 2,
        precip_mm_p50=precip_p50,
        precip_mm_p90=precip_p50 * 2,
        tmax_c=tmax,
        tmin_c=tmax - 10,
        source="fixture",
        source_url="https://x",
        retrieved_at=run,
    )


# --- dormant feature builder ----------------------------------------------

def test_feature_is_none_when_no_link():
    # No DB needed: a series with no linked belt short-circuits before any read.
    assert weather_feature_for_series(None, commodity="Onion", market="Azadpur") is None


def test_feature_is_none_when_linked_but_no_forecast(session: Session):
    # Linked belt, but nothing stored -> None (access pending), never a zero-stress reading.
    assert (
        weather_feature_for_series(session, commodity="Onion", market="Lasalgaon") is None
    )


def test_feature_sums_precip_and_counts_heat_days(session: Session):
    session.add_all(
        [
            _forecast("nashik-onion", date(2026, 11, 15), precip_p50=5.0, tmax=30.0),
            _forecast("nashik-onion", date(2026, 11, 16), precip_p50=10.0, tmax=37.0),
            _forecast("nashik-onion", date(2026, 11, 17), precip_p50=2.5, tmax=36.0),
        ]
    )
    session.flush()

    f = weather_feature_for_series(session, commodity="Onion", market="Lasalgaon")
    assert f is not None
    assert f.precip_p50_sum_mm == 17.5
    assert f.heat_days == 2  # 37 and 36 clear 35°C; 30 does not
    assert f.n_days == 3
    assert f.zones == ["nashik-onion"]
    assert f.heat_threshold_c == 35.0


def test_heat_threshold_is_tunable(session: Session):
    session.add(_forecast("nashik-onion", date(2026, 11, 15), precip_p50=1.0, tmax=36.0))
    session.flush()
    hot = weather_feature_for_series(
        session, commodity="Onion", market="Lasalgaon", heat_threshold_c=40.0
    )
    assert hot is not None and hot.heat_days == 0  # 36 < 40 -> not a heat day
