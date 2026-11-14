"""Quantile price BAND (p10/p50/p90) - the Phase-2 product direction (M14).

A 5-method point forecaster already lost to the last-price anchor, so the product
is NOT a point prediction: it is a band a procurement operator acts on, plus a
margin watch. Two bands are built, per the agreed decision:

  * `conformal_band` - split-conformal residual quantiles around a baseline point
    forecaster (default seasonal_naive). This is BOTH the honest band-to-beat AND
    the labelled fallback served when the challenger does not clear the kill bar.
  * `quantile_gb_band` - a gradient-boosting quantile regressor fit for q in
    {0.1, 0.5, 0.9} on the shared feature matrix; the challenger.

Both return a `Band` with p10 <= p50 <= p90 (monotone enforced) and a lower bound
clamped at 0 (a price cannot be negative). The band only reaches serving where it
beats the anchor AND seasonal_naive per commodity on walk-forward (see kill.py);
RISK[R7-FORECAST-BAR] and R13 apply unchanged - the band inherits them, it does
not escape them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vervana.forecast.baselines import Forecast, seasonal_naive
from vervana.forecast.features import build_features, feature_row

# The band is p10/p50/p90 (an 80% nominal interval, decision 3a). Coverage is
# judged against the [0.75, 0.88] acceptance window in kill.py, never assumed.
QLOW, QMID, QHIGH = 0.1, 0.5, 0.9


@dataclass(frozen=True)
class Band:
    p10: float
    p50: float
    p90: float

    @property
    def width(self) -> float:
        return self.p90 - self.p10


def _as_band(p10: float, p50: float, p90: float) -> Band:
    """Enforce monotonicity and the non-negativity domain constraint."""
    lo, mid, hi = sorted((p10, p50, p90))
    return Band(p10=max(0.0, lo), p50=max(0.0, mid), p90=max(0.0, hi))


def conformal_band(
    history: np.ndarray, *, base=seasonal_naive, min_cal: int = 8
) -> Band:
    """Split-conformal band: baseline point + empirical residual quantiles.

    Residuals come from a one-step expanding replay of `base` over the history (no
    look-ahead: each residual uses only past data). With too few residuals it
    falls back to the baseline's own +/- z*sigma interval, mapped to p10/p50/p90.
    """
    history = np.asarray(history, dtype=float)
    base_point = base(history).point
    resid = []
    for t in range(min_cal, history.size):
        resid.append(history[t] - base(history[:t]).point)
    if len(resid) < min_cal:
        fc: Forecast = base(history)
        return _as_band(fc.low, fc.point, fc.high)
    r = np.array(resid, dtype=float)
    return _as_band(
        base_point + float(np.quantile(r, QLOW)),
        base_point + float(np.quantile(r, QMID)),
        base_point + float(np.quantile(r, QHIGH)),
    )


def quantile_gb_band(history: np.ndarray, *, n_lags: int = 7) -> Band:
    """Gradient-boosting quantile band. Falls back to the conformal band when there
    is too little history to fit (never fabricates a confident band from nothing)."""
    history = np.asarray(history, dtype=float)
    if history.size < n_lags + 8:
        return conformal_band(history)
    from sklearn.ensemble import HistGradientBoostingRegressor

    X, y = build_features(history, n_lags)
    row = np.array([feature_row(history, n_lags)], dtype=float)
    preds: list[float] = []
    for q in (QLOW, QMID, QHIGH):
        model = HistGradientBoostingRegressor(
            loss="quantile", quantile=q, max_iter=120, max_depth=3, learning_rate=0.08
        )
        model.fit(X, y)
        preds.append(float(model.predict(row)[0]))
    return _as_band(*preds)


BANDS = {"conformal": conformal_band, "quantile_gb": quantile_gb_band}
