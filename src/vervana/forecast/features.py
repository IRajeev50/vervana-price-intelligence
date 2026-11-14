"""Supervised features for the price band (M14).

Univariate by necessity: the only per-day signal in the store today is the price
itself (see below). Features are price lags, short rolling statistics, and a
positional weekly term - the same information the existing gradient-boosting point
model uses, exposed here as a reusable matrix the quantile band can share.

TWO feature groups are deliberately WIRED BUT EMPTY, so the band can be
backtested with and without them the day they exist - never faked before:
  * `weather`  - origin-belt rain percentiles / heat days from WeatherNext
    (Phase 1 feed; access pending, so zero columns now);
  * `arrivals` - Agmarknet market arrivals. HONEST FINDING (M14): arrivals are
    NOT stored. PriceObservation has no arrivals column and the archived
    `raw_quote` carries only arrival_DATE, not the arrivals quantity - so the
    arrival-shock feature cannot be built from existing data. It needs a capture
    change (store arrivals going forward); documented in M14-done.md, not faked.
"""

from __future__ import annotations

import numpy as np

FEATURE_NAMES_BASE = None  # set lazily by build_features for the chosen n_lags


def _rolling(a: np.ndarray, window: int, fn) -> float:
    w = a[-window:] if a.size >= 1 else a
    return float(fn(w)) if w.size else 0.0


def feature_row(history: np.ndarray, n_lags: int = 7) -> list[float]:
    """The single feature vector for the next-step prediction from `history`."""
    lags = [float(history[-k]) for k in range(1, n_lags + 1)]
    roll_mean = _rolling(history, 7, np.mean)
    roll_std = _rolling(history, 7, np.std)
    dow = float(history.size % 7)  # positional weekly term (matches models.py)
    return [*lags, roll_mean, roll_std, dow]


def build_features(history: np.ndarray, n_lags: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, y) for supervised fitting over `history` (oldest->newest).

    Row t (for t >= n_lags) predicts history[t] from the n_lags preceding values
    plus rolling mean/std of the window up to t and a positional weekly term.
    """
    X, y = [], []
    for t in range(n_lags, history.size):
        window = history[:t]
        lags = [float(history[t - k]) for k in range(1, n_lags + 1)]
        X.append(
            [*lags, _rolling(window, 7, np.mean), _rolling(window, 7, np.std), float(t % 7)]
        )
        y.append(float(history[t]))
    return np.array(X, dtype=float), np.array(y, dtype=float)
