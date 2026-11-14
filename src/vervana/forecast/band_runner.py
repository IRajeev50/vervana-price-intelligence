"""Run the band backtest across the store and apply the per-commodity kill (M14).

For every (commodity, mandi) executed_summary series with enough history: backtest
the anchor (naive), seasonal_naive, the conformal baseline band, and the
quantile-GB challenger; decide per series whether the challenger ships
(evaluate_band_kill); then roll up per commodity by MAJORITY of its qualifying
mandis (decision: per-commodity majority). Results persist to band_latest.json;
nothing is served unless it is recorded there.

HONEST EXPECTATION (M14): the executed_summary history is thin - the deepest
series is ~27 distinct days, so each walk-forward yields only a handful of
one-step test points. The band machinery is real and tested, but with this little
history and NO weather features yet, the honest prior is that few or no
commodities clear the bar. Negative results are the expected, documented output.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass
from vervana.forecast.backtest import walk_forward, walk_forward_band
from vervana.forecast.band import conformal_band, quantile_gb_band
from vervana.forecast.baselines import naive, seasonal_naive
from vervana.forecast.kill import decide_commodity, evaluate_band_kill, save_band_results
from vervana.forecast.series import price_series
from vervana.models.entities import Commodity, Market
from vervana.models.observations import PriceObservation
from vervana.time import now_utc


def _qualifying_series(session: Session, *, min_days: int) -> list[tuple[int, int, str, str, int]]:
    """(commodity_id, market_id, commodity_name, market_name, n_days) with >= min_days
    distinct executed_summary days."""
    day = func.date(PriceObservation.observed_at)
    rows = session.execute(
        select(
            PriceObservation.commodity_id,
            PriceObservation.market_id,
            func.count(func.distinct(day)).label("d"),
        )
        .where(
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
        .group_by(PriceObservation.commodity_id, PriceObservation.market_id)
        .having(func.count(func.distinct(day)) >= min_days)
    ).all()
    out = []
    for cid, mid, d in rows:
        c = session.get(Commodity, cid)
        m = session.get(Market, mid)
        if c and m:
            out.append((cid, mid, c.canonical_name, m.canonical_name, int(d)))
    return out


def backtest_bands(session: Session, *, min_train: int = 14, min_days: int = 20) -> dict:
    """Backtest the band across the store; return a persisted summary payload."""
    per_series: list[dict] = []
    commodity_pass: dict[str, list[bool]] = {}

    for cid, mid, cname, mname, _d in _qualifying_series(session, min_days=min_days):
        series = price_series(session, commodity_id=cid, market_id=mid)
        if series.size <= min_train + 1:
            continue
        try:
            anchor = walk_forward(series, naive, min_train=min_train)
            seasonal = walk_forward(series, seasonal_naive, min_train=min_train)
            chal = walk_forward_band(series, quantile_gb_band, min_train=min_train)
            base = walk_forward_band(series, conformal_band, min_train=min_train)
        except ValueError:
            continue
        decision = evaluate_band_kill(
            band_mae=chal.p50_mae_paise,
            band_wape=chal.p50_wape,
            coverage=chal.coverage,
            anchor_mae=anchor.mae_paise,
            anchor_wape=anchor.wape,
            seasonal_mae=seasonal.mae_paise,
            seasonal_wape=seasonal.wape,
        )
        commodity_pass.setdefault(cname, []).append(decision.shippable)
        per_series.append(
            {
                "commodity": cname,
                "market": mname,
                "n": chal.n,
                "challenger_p50_mae_paise": round(chal.p50_mae_paise, 1),
                "challenger_wape": round(chal.p50_wape, 4),
                "challenger_coverage": round(chal.coverage, 4),
                "challenger_width_paise": round(chal.mean_width_paise, 1),
                "baseline_band_coverage": round(base.coverage, 4),
                "anchor_mae_paise": round(anchor.mae_paise, 1),
                "anchor_wape": round(anchor.wape, 4),
                "seasonal_mae_paise": round(seasonal.mae_paise, 1),
                "seasonal_wape": round(seasonal.wape, 4),
                "shippable": decision.shippable,
                "reason": decision.reason,
            }
        )

    per_commodity = {
        cname: {
            "shippable": decide_commodity(flags),
            "n_mandis": len(flags),
            "n_pass": sum(flags),
            "reason": (
                f"{sum(flags)}/{len(flags)} qualifying mandis beat anchor+seasonal with "
                f"in-window coverage"
            ),
        }
        for cname, flags in commodity_pass.items()
    }
    payload = {
        "made_at": now_utc().isoformat(),
        "min_train": min_train,
        "min_days": min_days,
        "n_series": len(per_series),
        "n_commodities": len(per_commodity),
        "n_commodities_shippable": sum(1 for v in per_commodity.values() if v["shippable"]),
        "per_commodity": per_commodity,
        "per_series": per_series,
    }
    save_band_results(payload)
    return payload


def format_band_summary(payload: dict) -> str:
    lines = [
        "Price-band backtest (expanding-window walk-forward, p10/p50/p90)",
        f"series={payload['n_series']}  commodities={payload['n_commodities']}  "
        f"shippable={payload['n_commodities_shippable']}",
        "",
        f"{'commodity':<24}{'mandis':>7}{'pass':>6}{'ship?':>7}",
    ]
    for cname, v in sorted(payload["per_commodity"].items()):
        ship = "YES" if v["shippable"] else "no"
        lines.append(f"{cname[:24]:<24}{v['n_mandis']:>7}{v['n_pass']:>6}{ship:>7}")
    if payload["n_commodities_shippable"] == 0:
        lines.append("")
        lines.append(
            "No commodity's band beat the anchor + seasonal with in-window coverage — "
            "serving the labelled baseline band everywhere (honest negative result)."
        )
    return "\n".join(lines)
