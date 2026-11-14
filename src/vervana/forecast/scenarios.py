"""Weather-gated band scenarios (M14, scaffolded - inert until weather exists).

The band maps forward weather to labelled DECISIONS, never a naked number:
  * `rain-crushes-arrivals` - heavy origin-belt rain -> expected arrival drop ->
    upward price pressure in N days;
  * `heat-spike` - an origin heat wave -> shelf-life / QC-rejection risk.

Each is a labelled Scenario with its evidence or it does not fire. Weather
features do not exist yet (WeatherNext access pending; arrivals not stored), so
`detect_scenarios` returns NOTHING - it fabricates no scenario from absent data.
The thresholds live here so that the day the weather feature group is populated,
switching scenarios on is a one-line change, fully reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    label: str  # rain-crushes-arrivals | heat-spike
    evidence: str  # the concrete signal that fired it
    direction: str  # "up" | "watch"


def detect_scenarios(*, weather_features: dict | None = None) -> list[Scenario]:
    """Return labelled scenarios from the weather feature group, or [] when it is
    empty. No weather features in the store yet -> always [] (never invented)."""
    if not weather_features:
        return []
    # When the weather group lands, the thresholds below fire labelled scenarios.
    # Documented, reviewable, and OFF until there is real data to judge:
    #   rain-crushes-arrivals: belt precip p50 over the T-7..T-1 window above its
    #     seasonal normal by a documented margin -> Scenario("up").
    #   heat-spike: belt tmax over the window above a crop-specific threshold ->
    #     Scenario("watch").
    return []  # pragma: no cover - unreachable until weather_features is populated
