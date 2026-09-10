"""Forecast models: SARIMA then gradient boosting (§5.3). Heavy libs imported lazily.

Order is deliberate and non-negotiable: baselines first (baselines.py), then SARIMA
(marginally justified by ~90 obs + weekly seasonality), then gradient boosting. No LSTM
(there is nowhere near enough data — the spec forbids it and so do we).
"""

from __future__ import annotations

import numpy as np

from vervana.forecast.baselines import Forecast, naive

Z_90 = 1.645


def sarima(history: np.ndarray) -> Forecast:
    """SARIMA(1,0,0)(1,0,0)_7 one-step forecast; falls back to naive on too little data
    or a fit failure. Weekly seasonality only — annual seasonality is unlearnable from
    ~90 days and we do not claim it."""
    history = np.asarray(history, dtype=float)
    if history.size < 21:
        return naive(history)
    try:
        import warnings

        from statsmodels.tsa.statespace.sarimax import SARIMAX

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = SARIMAX(
                history,
                order=(1, 0, 0),
                seasonal_order=(1, 0, 0, 7),
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False)
        fc = model.get_forecast(1)
        point = float(fc.predicted_mean[0])
        ci = fc.conf_int(alpha=0.10)
        low, high = float(ci[0][0]), float(ci[0][1])
        return Forecast(point=point, low=low, high=high)
    except Exception:
        return naive(history)


def _lag_matrix(series: np.ndarray, n_lags: int):
    X, y = [], []
    for t in range(n_lags, series.size):
        X.append([series[t - k] for k in range(1, n_lags + 1)] + [t % 7])
        y.append(series[t])
    return np.array(X, dtype=float), np.array(y, dtype=float)


def gradient_boosting(history: np.ndarray, n_lags: int = 7) -> Forecast:
    # RISK[R7-FORECAST-BAR]: This assumes gradient boosting can beat the naive baselines on
    # next-day fresh-produce prices. Daily F&V prices are close to a random walk with
    # weather shocks, and ~90 obs/series is too little for a tree model to generalise
    # per-series. The backtest ALWAYS reports this model beside the three baselines, and
    # the kill criterion (kill.py) blocks it from serving unless it clears the bar.
    # Evidence: docs/RISK_REGISTER.md#r7-forecast-bar
    # Verdict: PENDING (no real multi-day history captured yet; see M4-done)

    # RISK[R6-MOAT-MODEL-GAP]: The corpus is pitched as the moat, yet the model trains on
    # Agmarknet history — both cannot be load-bearing. Feature importance is logged every
    # run and the aggregate contribution of video-derived features is reported; under 5%
    # means the corpus does not defend the forecast. Right now there are ZERO video-derived
    # features (Gate 1), so video contribution is 0% by construction — the corpus defends
    # nothing in this model until/unless transcripts are ingested and prove predictive.
    # Evidence: docs/RISK_REGISTER.md#r6-moat-model-gap
    # Verdict: PENDING — video-feature contribution = 0% (no video features exist yet)
    history = np.asarray(history, dtype=float)
    if history.size < n_lags + 5:
        return naive(history)
    from sklearn.ensemble import HistGradientBoostingRegressor

    X, y = _lag_matrix(history, n_lags)
    model = HistGradientBoostingRegressor(max_iter=120, max_depth=3, learning_rate=0.08)
    model.fit(X, y)
    feat = np.array([[history[-k] for k in range(1, n_lags + 1)] + [history.size % 7]], dtype=float)
    point = float(model.predict(feat)[0])
    resid = y - model.predict(X)
    sigma = float(np.std(resid))
    return Forecast(point=point, low=point - Z_90 * sigma, high=point + Z_90 * sigma)


MODELS = {"sarima": sarima, "gradient_boosting": gradient_boosting}
