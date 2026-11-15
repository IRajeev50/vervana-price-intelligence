"""Weather feature builder for the price band (M20a, W4 — DORMANT seam).

The band is univariate today (forecast/features.py). This module is the ready-but-dormant
bridge: given a (commodity, mandi) series, it finds the belts whose weather informs it
(W3 link, supply_zones.mandis), reads their stored WeatherNext forecast rows, and reduces
them to a small forward-supply-stress feature. It is NOT wired into the live band or kill
gate — that happens in M20b, once real forecasts exist and the BigQuery column mapping is
confirmed against the live catalog, AND only if a walk-forward backtest proves the feature
beats the anchor + seasonal baseline. Until then this stays off the serving path.

Honesty notes carried from the WeatherNext seam (M13):
- A forecast is never a price and never a chain signal; weather_forecast is its own table.
- Precip percentiles are the daily SUM of hourly percentile values — a usable approximation,
  not an exact daily quantile. Labelled as an approximation everywhere.
- Returns None when no forecast rows exist, so "access pending / no data" is never mistaken
  for a zero-stress reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vervana.repository.weather_forecast import latest_run_for_zone
from vervana.supply.zones import zones_for_series

# A heat-stress day is one whose forecast tmax clears this threshold. 35°C is a deliberate
# default assumption (RISK: per-commodity calibration is an M20b task, tuned on real data).
DEFAULT_HEAT_THRESHOLD_C = 35.0


@dataclass(frozen=True)
class WeatherFeature:
    """A series' forward supply-stress feature from its linked belts' latest forecast run.

    All fields are approximations labelled as such; this is a feature candidate for M20b's
    backtest, never a statement of fact about the weather.
    """

    precip_p50_sum_mm: float  # sum of daily precip p50 over the forecast horizon
    heat_days: int  # count of forecast days with tmax >= threshold
    n_days: int  # how many forecast days contributed
    zones: list[str] = field(default_factory=list)  # the belts that informed it
    heat_threshold_c: float = DEFAULT_HEAT_THRESHOLD_C


def weather_feature_for_series(
    session,
    *,
    commodity: str,
    market: str,
    heat_threshold_c: float = DEFAULT_HEAT_THRESHOLD_C,
) -> WeatherFeature | None:
    """Reduce the latest forecast run of a series' linked belts to a supply-stress feature.

    Returns None when the series has no linked belt, or no belt has any stored forecast row
    (access pending) — never a fabricated zero. Pure w.r.t. the store: it only reads.
    """
    zones = zones_for_series(commodity, market)
    if not zones:
        return None

    precip_sum = 0.0
    heat_days = 0
    n_days = 0
    contributing: list[str] = []
    for z in zones:
        rows = latest_run_for_zone(session, z.zone)
        if not rows:
            continue
        contributing.append(z.zone)
        for r in rows:
            n_days += 1
            if r.precip_mm_p50 is not None:
                precip_sum += float(r.precip_mm_p50)
            if r.tmax_c is not None and float(r.tmax_c) >= heat_threshold_c:
                heat_days += 1
    if not contributing:
        return None  # linked, but no forecast stored yet (access pending) — not zero-stress

    return WeatherFeature(
        precip_p50_sum_mm=round(precip_sum, 3),
        heat_days=heat_days,
        n_days=n_days,
        zones=contributing,
        heat_threshold_c=heat_threshold_c,
    )
