"""Walk-forward backtest + metrics + decision-level P&L (§5.3).

The evaluation harness matters more than the models. Rules enforced here:
  * Expanding-window walk-forward only — NEVER a random split (no leakage).
  * Metrics reported per series: MAE (₹/kg), sMAPE, directional accuracy, PI coverage.
  * A decision-level metric: simulated P&L of a buy/hold/sell rule driven by the forecast
    vs the same rule driven by naive.

All forecasters (baselines and models) go through the same harness so their numbers are
comparable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from vervana.forecast.baselines import Forecast, naive

Forecaster = Callable[[np.ndarray], Forecast]


@dataclass
class BacktestResult:
    name: str
    n: int
    mae_paise: float
    smape: float
    directional_accuracy: float
    pi_coverage: float
    pnl_vs_naive: float
    preds: list[float] = field(default_factory=list)
    actuals: list[float] = field(default_factory=list)


def _smape(actual: np.ndarray, pred: np.ndarray) -> float:
    denom = (np.abs(actual) + np.abs(pred)) / 2.0
    mask = denom != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs(actual[mask] - pred[mask]) / denom[mask]))


def walk_forward(
    series: np.ndarray, forecaster: Forecaster, *, min_train: int = 14
) -> BacktestResult:
    """One-step-ahead expanding-window backtest over `series` (oldest→newest)."""
    series = np.asarray(series, dtype=float)
    if series.size <= min_train:
        raise ValueError(f"need > {min_train} points, got {series.size}")

    preds, lows, highs, actuals, prevs = [], [], [], [], []
    for t in range(min_train, series.size):
        history = series[:t]
        fc = forecaster(history)
        preds.append(fc.point)
        lows.append(fc.low)
        highs.append(fc.high)
        actuals.append(series[t])
        prevs.append(series[t - 1])

    preds_a, actuals_a = np.array(preds), np.array(actuals)
    lows_a, highs_a, prevs_a = np.array(lows), np.array(highs), np.array(prevs)

    mae = float(np.mean(np.abs(preds_a - actuals_a)))
    smape = _smape(actuals_a, preds_a)
    # Directional accuracy: did we get the up/down move vs the previous day right?
    pred_dir = np.sign(preds_a - prevs_a)
    actual_dir = np.sign(actuals_a - prevs_a)
    directional = float(np.mean(pred_dir == actual_dir))
    coverage = float(np.mean((actuals_a >= lows_a) & (actuals_a <= highs_a)))
    pnl = _pnl_vs_naive(series, preds_a, actuals_a, prevs_a, min_train)

    return BacktestResult(
        name=getattr(forecaster, "__name__", "forecaster"),
        n=len(preds),
        mae_paise=mae,
        smape=smape,
        directional_accuracy=directional,
        pi_coverage=coverage,
        pnl_vs_naive=pnl,
        preds=preds,
        actuals=actuals,
    )


def _pnl_vs_naive(series, preds, actuals, prevs, min_train) -> float:
    """A/B P&L: a simple rule (buy if forecast says up, else hold) driven by the model
    vs by naive. Returns model_pnl - naive_pnl in paise/kg (positive = model helped).

    Rule: if forecast > today, 'buy today, sell tomorrow' → gain = actual - today.
    Otherwise no position → 0. Same rule for both, only the signal differs.
    """
    naive_preds = np.array([naive(series[:t]).point for t in range(min_train, series.size)])

    def strat_pnl(signal_preds):
        buy = signal_preds > prevs
        return float(np.sum((actuals - prevs)[buy]))

    return strat_pnl(preds) - strat_pnl(naive_preds)
