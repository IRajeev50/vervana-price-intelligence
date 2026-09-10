"""Forecasting baselines (§5.3). These are ALWAYS computed and reported — no model
ships without being compared to all three.

Each forecaster takes a history (1-D array of daily prices, oldest→newest) and returns a
one-step-ahead Forecast with a point and a prediction interval. The interval for the
baselines is a simple ±z·σ from the history's first differences, so prediction-interval
coverage is measurable even for the naive models.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Z_90 = 1.645  # ~90% two-sided normal interval


@dataclass
class Forecast:
    point: float
    low: float
    high: float


def _interval(point: float, history: np.ndarray, z: float = Z_90) -> Forecast:
    diffs = np.diff(history)
    sigma = float(np.std(diffs)) if diffs.size else 0.0
    # A price cannot be negative — clamp the lower bound at 0 (a domain constraint).
    return Forecast(point=point, low=max(0.0, point - z * sigma), high=point + z * sigma)


def naive(history: np.ndarray) -> Forecast:
    """Tomorrow = today."""
    return _interval(float(history[-1]), history)


def seasonal_naive(history: np.ndarray, period: int = 7) -> Forecast:
    """Same weekday last week (falls back to naive if history is shorter than a period)."""
    point = float(history[-period]) if history.size > period else float(history[-1])
    return _interval(point, history)


def moving_average(history: np.ndarray, window: int = 7) -> Forecast:
    """Mean of the last `window` days."""
    w = min(window, history.size)
    return _interval(float(np.mean(history[-w:])), history)


BASELINES = {
    "naive": naive,
    "seasonal_naive": seasonal_naive,
    "moving_average": moving_average,
}
