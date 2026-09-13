"""NDVI -> signal mapping (M11). Pure functions: no network, no database.

Sentinel-2 NDVI is a vegetation-vigour estimate, not a measurement of traded
supply; the anomaly (current window minus the same window a year earlier) is
what feeds the chain's `ndvi_anomaly` kind, so a one-off cloudy season reads as
an anomaly only against its own baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from vervana.intelligence.signals import Signal, SignalStatus

#: Sentinel-2 L2A via the Copernicus Data Space Statistical API (free tier).
SENTINEL2_SOURCE = "Sentinel-2 L2A via Copernicus Data Space"
SENTINEL2_SOURCE_URL = "https://dataspace.copernicus.eu/"


@dataclass(frozen=True)
class NdviWindow:
    """One zone's NDVI for the current window and its year-ago baseline."""

    zone: str
    district: str
    state: str
    on_date: date
    current_mean: float
    baseline_mean: float


def anomaly_value(current_mean: float, baseline_mean: float) -> float:
    """NDVI anomaly vs the year-ago same-window baseline (dimensionless, -2..2)."""
    return round(current_mean - baseline_mean, 4)


def windows_to_signals(windows: list[NdviWindow]) -> list[Signal]:
    """Map validated NDVI windows to OBSERVED ndvi_anomaly signals."""
    out: list[Signal] = []
    for w in windows:
        out.append(
            Signal(
                kind="ndvi_anomaly",
                region=w.district,
                on_date=w.on_date,
                value_numeric=anomaly_value(w.current_mean, w.baseline_mean),
                value_text=None,
                status=SignalStatus.observed,
                source=SENTINEL2_SOURCE,
                source_url=SENTINEL2_SOURCE_URL,
                note=(
                    f"zone {w.zone}: current {w.current_mean:.3f} vs year-ago {w.baseline_mean:.3f}"
                ),
            )
        )
    return out
