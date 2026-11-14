"""Quantile price band: construction, metrics, kill discipline, margin watch.

Offline, no DB/network. Calibration uses a longer synthetic series so coverage is
stable; the kill and margin logic are pure and checked at their boundaries.
"""

from __future__ import annotations

import numpy as np
import pytest

from vervana.forecast import kill as killmod
from vervana.forecast.backtest import _wape, walk_forward_band
from vervana.forecast.band import Band, conformal_band, quantile_gb_band
from vervana.forecast.kill import (
    BAND_COV_HI,
    BAND_COV_LO,
    decide_commodity,
    evaluate_band_kill,
    load_band_decision,
)
from vervana.forecast.margin import margin_watch


def test_band_is_monotone_and_nonnegative():
    b = conformal_band(np.array([10.0, -5.0, 20.0, 8.0, 12.0, 9.0, 11.0, 10.0, 13.0, 7.0]))
    assert b.p10 <= b.p50 <= b.p90
    assert b.p10 >= 0.0  # price cannot be negative
    assert b.width == b.p90 - b.p10


def test_conformal_coverage_is_near_nominal_on_a_long_series():
    rng = np.random.default_rng(0)
    series = 2000 + np.cumsum(rng.normal(0, 30, 400))  # random walk, paise
    res = walk_forward_band(series, conformal_band, min_train=30)
    # p10-p90 is an 80% nominal interval; realized coverage should sit near it.
    assert 0.6 <= res.coverage <= 0.95
    assert res.mean_width_paise > 0


def test_quantile_gb_band_monotone_and_short_history_fallback():
    short = np.array([100.0, 101.0, 99.0, 100.0])  # too short -> conformal fallback
    b = quantile_gb_band(short)
    assert b.p10 <= b.p50 <= b.p90
    rng = np.random.default_rng(1)
    long = 500 + np.cumsum(rng.normal(0, 10, 120))
    b2 = quantile_gb_band(long)
    assert b2.p10 <= b2.p50 <= b2.p90


def test_wape_exact():
    actual = np.array([100.0, 200.0, 300.0])
    pred = np.array([110.0, 190.0, 300.0])
    assert _wape(actual, pred) == pytest.approx((10 + 10 + 0) / 600.0)
    assert _wape(np.zeros(3), np.ones(3)) == 0.0  # all-zero actuals -> 0, not inf


def test_evaluate_band_kill_ships_only_when_all_conditions_hold():
    good_cov = (BAND_COV_LO + BAND_COV_HI) / 2
    # Beats both on MAE and WAPE, coverage in window -> ships.
    d = evaluate_band_kill(
        band_mae=90, band_wape=0.04, coverage=good_cov,
        anchor_mae=100, anchor_wape=0.05, seasonal_mae=95, seasonal_wape=0.045,
    )
    assert d.shippable
    # Coverage too low -> no ship.
    d2 = evaluate_band_kill(
        band_mae=90, band_wape=0.04, coverage=BAND_COV_LO - 0.1,
        anchor_mae=100, anchor_wape=0.05, seasonal_mae=95, seasonal_wape=0.045,
    )
    assert not d2.shippable and "coverage" in d2.reason
    # Loses on MAE (not below seasonal) -> no ship.
    d3 = evaluate_band_kill(
        band_mae=96, band_wape=0.04, coverage=good_cov,
        anchor_mae=100, anchor_wape=0.05, seasonal_mae=95, seasonal_wape=0.045,
    )
    assert not d3.shippable and "MAE" in d3.reason


def test_decide_commodity_majority():
    assert decide_commodity([True, True, False]) is True
    assert decide_commodity([True, False]) is False  # tie is not a majority
    assert decide_commodity([]) is False  # fail closed


def test_margin_watch_zones():
    band = Band(p10=1000, p50=1500, p90=2000)
    assert margin_watch(900, band).zone == "below-band"
    assert margin_watch(1200, band).zone == "favorable"
    assert margin_watch(1500, band).zone == "watch"  # == p50 is upper half
    assert margin_watch(1800, band).zone == "watch"
    assert margin_watch(2100, band).zone == "caution"


def test_load_band_decision_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(killmod, "BAND_RESULTS_PATH", tmp_path / "nope.json")
    d = load_band_decision("Onion")
    assert d.shippable is False and "no band backtest" in d.reason
