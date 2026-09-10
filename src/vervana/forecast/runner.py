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


def pick_model() -> str:
    """The model the serving layer is allowed to use: the real model only if the kill
    criterion passed, else the seasonal-naive baseline (per R7)."""
    from vervana.forecast.kill import load_decision

    return "gradient_boosting" if load_decision().model_shippable else "seasonal_naive"


def run_prospective_basket(
    session: Session, *, commodities: list[str], market_name: str = "Azadpur", min_history: int = 21
) -> list[dict]:
    """Record tomorrow's call for each commodity (Delhi video series, units applied).

    Append-only, published unedited. The model is chosen by the kill criterion, so when
    the model is not shippable we post the labelled baseline + interval, never a bare
    'AI forecast'."""
    from sqlalchemy import select

    from vervana.analytics.unit_inference import infer_units
    from vervana.forecast.series import quote_midpoint_series
    from vervana.models.entities import Commodity, Market

    model = pick_model()
    market = session.scalar(select(Market).where(Market.canonical_name == market_name))
    if market is None:
        return []
    units = infer_units(session)
    recorded = []
    for name in commodities:
        c = session.scalar(select(Commodity).where(Commodity.canonical_name == name))
        if c is None:
            continue
        u = units.get(name)
        if u is None or u.scale_to_kg is None:
            continue  # unit unknown -> can't express a ₹/kg forecast honestly; skip
        series = quote_midpoint_series(session, commodity_id=c.id, market_id=market.id)
        if len(series) <= min_history:
            continue
        record_prospective(
            session, commodity_id=c.id, market_id=market.id, model=model, series=series
        )
        recorded.append({"commodity": name, "model": model, "n_history": len(series)})
    return recorded


def video_actual_lookup(session: Session):
    """Build an actual-price lookup from the Delhi video series (units applied, ₹/kg paise)."""
    import statistics
    from collections import defaultdict

    from vervana.analytics.unit_inference import infer_units
    from vervana.db.base import SourceClass
    from vervana.models.entities import Commodity
    from vervana.models.observations import PriceObservation

    units = infer_units(session)
    vals: dict[tuple[int, int, object], list[float]] = defaultdict(list)
    for r in session.scalars(
        select(PriceObservation).where(
            PriceObservation.source_class == SourceClass.quote_indicative
        )
    ):
        cname = session.get(Commodity, r.commodity_id).canonical_name
        u = units.get(cname)
        scale = u.scale_to_kg if (u and u.scale_to_kg) else 1.0
        key = (r.commodity_id, r.market_id, to_ist(r.observed_at).date())
        vals[key].append((r.price_low_paise + r.price_high_paise) / 2 * scale)

    def lookup(commodity_id: int, market_id: int, target_date) -> int | None:
        key = (commodity_id, market_id, target_date)
        if key not in vals:
            return None
        return round(statistics.median(vals[key]))  # median, robust to outliers

    return lookup


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


def prospective_summary(session: Session, limit: int = 50) -> dict:
    """Aggregate the public prospective log: counts, MAE, interval hit-rate + recent rows."""
    from vervana.models.entities import Commodity, Market
    from vervana.models.forecast_log import ProspectiveForecast

    rows = list(
        session.scalars(
            select(ProspectiveForecast)
            .order_by(ProspectiveForecast.target_date.desc(), ProspectiveForecast.id.desc())
            .limit(limit)
        )
    )
    scored = [r for r in rows if r.actual_paise is not None]
    mae = round(sum(r.abs_error_paise for r in scored) / len(scored) / 100, 2) if scored else None
    hit_rate = round(sum(1 for r in scored if r.hit_interval) / len(scored), 3) if scored else None
    recent = []
    for r in rows:
        recent.append(
            {
                "commodity": session.get(Commodity, r.commodity_id).canonical_name,
                "market": session.get(Market, r.market_id).canonical_name,
                "target_date": r.target_date.isoformat(),
                "model": r.model,
                "point": round(r.point_paise / 100, 2),
                "low": round(r.low_paise / 100, 2),
                "high": round(r.high_paise / 100, 2),
                "actual": None if r.actual_paise is None else round(r.actual_paise / 100, 2),
                "hit": r.hit_interval,
            }
        )
    return {
        "n_calls": len(rows),
        "n_scored": len(scored),
        "mae_rupees": mae,
        "interval_hit_rate": hit_rate,
        "recent": recent,
    }
