"""Tie the harness together: backtest all forecasters, apply the kill criterion, and
manage the prospective log."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.forecast.backtest import BacktestResult, walk_forward
from vervana.forecast.baselines import BASELINES
from vervana.forecast.kill import evaluate_kill, save_results
from vervana.forecast.models import MODELS
from vervana.time import now_utc, to_ist

ALL_FORECASTERS = {**BASELINES, **MODELS}


def backtest_all(series: np.ndarray, *, min_train: int = 14) -> dict[str, BacktestResult]:
    out: dict[str, BacktestResult] = {}
    for name, fn in ALL_FORECASTERS.items():
        try:
            res = walk_forward(series, fn, min_train=min_train)
            res.name = name
            out[name] = res
        except Exception:
            continue
    return out


def summarize_and_persist(results: dict[str, BacktestResult]) -> dict:
    gb = results.get("gradient_boosting")
    sn = results.get("seasonal_naive")
    decision = None
    if gb and sn:
        decision = evaluate_kill(gb.directional_accuracy, sn.directional_accuracy)
    payload = {
        "made_at": now_utc().isoformat(),
        "per_model": {
            k: {
                "mae_paise": round(v.mae_paise, 1),
                "smape": round(v.smape, 4),
                "directional_accuracy": round(v.directional_accuracy, 4),
                "pi_coverage": round(v.pi_coverage, 4),
                "pnl_vs_naive_paise": round(v.pnl_vs_naive, 1),
                "n": v.n,
            }
            for k, v in results.items()
        },
        "gradient_boosting_directional": gb.directional_accuracy if gb else None,
        "seasonal_naive_directional": sn.directional_accuracy if sn else None,
        "model_shippable": decision.model_shippable if decision else False,
        "kill_reason": decision.reason if decision else "insufficient data for a decision",
    }
    save_results(payload)
    return payload


def format_backtest(results: dict[str, BacktestResult]) -> str:
    lines = ["Walk-forward backtest (expanding window, 1-step)"]
    lines.append(
        f"{'model':<20}{'MAE ₹/kg':>10}{'sMAPE':>9}{'dir.acc':>9}{'PIcov':>8}{'P&L vs naive':>14}"
    )
    for name in ("naive", "seasonal_naive", "moving_average", "sarima", "gradient_boosting"):
        r = results.get(name)
        if not r:
            continue
        lines.append(
            f"{name:<20}{r.mae_paise / 100:>10.2f}{r.smape:>9.1%}"
            f"{r.directional_accuracy:>9.1%}{r.pi_coverage:>8.0%}{r.pnl_vs_naive / 100:>14.2f}"
        )
    return "\n".join(lines)


# --- prospective log ------------------------------------------------------------------
def record_prospective(
    session: Session, *, commodity_id: int, market_id: int, model: str, series: np.ndarray
) -> None:
    """Make and store tomorrow's call from `model` (append-only, published unedited)."""
    from vervana.forecast.runner import ALL_FORECASTERS
    from vervana.models.forecast_log import ProspectiveForecast

    fc = ALL_FORECASTERS[model](series)
    target = to_ist(now_utc()).date() + timedelta(days=1)
    session.add(
        ProspectiveForecast(
            commodity_id=commodity_id,
            market_id=market_id,
            target_date=target,
            made_at=now_utc(),
            model=model,
            point_paise=round(fc.point),
            low_paise=round(fc.low),
            high_paise=round(fc.high),
        )
    )
    session.flush()


def score_due(session: Session, actual_lookup) -> int:
    """Score forecasts whose target_date has passed. `actual_lookup(commodity_id,
    market_id, target_date) -> int|None` returns the realised ₹/kg (paise). Returns the
    number scored."""
    from vervana.models.forecast_log import ProspectiveForecast

    today = to_ist(now_utc()).date()
    scored = 0
    due = session.scalars(
        select(ProspectiveForecast).where(
            ProspectiveForecast.actual_paise.is_(None),
            ProspectiveForecast.target_date < today,
        )
    ).all()
    for f in due:
        actual = actual_lookup(f.commodity_id, f.market_id, f.target_date)
        if actual is None:
            continue
        f.actual_paise = actual
        f.abs_error_paise = abs(actual - f.point_paise)
        f.hit_interval = bool(f.low_paise <= actual <= f.high_paise)
        scored += 1
    session.flush()
    return scored
