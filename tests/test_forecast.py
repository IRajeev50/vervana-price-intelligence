"""Forecasting: baselines, walk-forward (no leakage), kill criterion both ways."""

from __future__ import annotations

import numpy as np

from vervana.forecast.backtest import walk_forward
from vervana.forecast.baselines import moving_average, naive, seasonal_naive
from vervana.forecast.kill import evaluate_kill
from vervana.forecast.runner import backtest_all, summarize_and_persist


def test_baselines():
    h = np.array([10, 11, 12, 13, 14, 15, 16, 17], dtype=float)
    assert naive(h).point == 17
    assert seasonal_naive(h, period=7).point == 11  # 7 back from the end
    assert moving_average(h, window=3).point == (15 + 16 + 17) / 3


def test_walk_forward_constant_series_is_perfect():
    # A flat series: naive predicts it exactly, MAE 0, and no leakage is possible.
    series = np.full(40, 500.0)
    r = walk_forward(series, naive, min_train=14)
    assert r.mae_paise == 0.0
    assert r.n == 40 - 14


def test_kill_criterion_fires_both_ways():
    assert evaluate_kill(0.75, 0.50).model_shippable is True  # clears +10%
    assert evaluate_kill(0.52, 0.50).model_shippable is False  # inside margin
    assert evaluate_kill(0.40, 0.50).model_shippable is False  # worse than baseline


def test_random_walk_model_not_shippable(tmp_path, monkeypatch):
    # On a random walk (like real F&V prices), GB should not clear seasonal-naive.
    import vervana.forecast.kill as killmod

    monkeypatch.setattr(killmod, "RESULTS_PATH", tmp_path / "latest.json")
    rng = np.random.default_rng(0)
    series = 2000 + np.cumsum(rng.normal(0, 40, 120))
    results = backtest_all(series, min_train=21)
    # all baselines present + at least one model attempted
    assert {"naive", "seasonal_naive", "moving_average"} <= set(results)
    summary = summarize_and_persist(results)
    assert summary["model_shippable"] is False
    assert "R7" in summary["kill_reason"] or "does NOT beat" in summary["kill_reason"]
