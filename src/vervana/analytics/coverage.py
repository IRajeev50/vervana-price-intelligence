"""Agmarknet Delhi coverage study (§5.1) — the experiment that tests the edge (R5).

For a market over a window, measures how complete and how timely Agmarknet's reporting
is: what fraction of expected commodity-days actually carry a price, how many are reported
same-day, the reporting-lag distribution, and how many implausible values slip through.

The whole product thesis rests on this being *bad*. So the verdict is written to state
plainly when it is GOOD (coverage high) — i.e. when the coverage edge does not exist.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass
from vervana.models.entities import Commodity, Market
from vervana.models.observations import PriceObservation
from vervana.time import to_ist

# Above this ₹/kg a fresh-vegetable price is almost certainly an error or a unit mix-up.
DEFAULT_SANITY_MAX_PAISE_PER_KG = 100_000  # ₹1000/kg
SAME_DAY_EDGE_THRESHOLD = 0.90  # R5: >90% same-day coverage => no coverage edge


@dataclass
class CoverageReport:
    market: str
    start: date
    end: date
    n_days: int
    tracked_commodities: int
    expected_commodity_days: int
    reported_commodity_days: int
    same_day_commodity_days: int
    implausible_values: int
    lag_histogram: dict[int, int] = field(default_factory=dict)
    per_commodity: dict[str, float] = field(default_factory=dict)

    @property
    def coverage_pct(self) -> float:
        return (
            self.reported_commodity_days / self.expected_commodity_days
            if self.expected_commodity_days
            else 0.0
        )

    @property
    def same_day_coverage_pct(self) -> float:
        return (
            self.same_day_commodity_days / self.expected_commodity_days
            if self.expected_commodity_days
            else 0.0
        )


def compute_coverage(
    session: Session,
    *,
    market_id: int,
    start: date,
    end: date,
    sanity_max_paise_per_kg: int = DEFAULT_SANITY_MAX_PAISE_PER_KG,
) -> CoverageReport:
    # RISK[R5-COVERAGE-EDGE]: The entire product edge assumes Agmarknet's Delhi coverage
    # is bad enough to beat. It is UNMEASURED; the documented failure is Assam, not Delhi.
    # This report measures it. If same-day coverage exceeds 90% of commodity-days, the
    # coverage advantage does not exist and only intraday timing remains — say so plainly.
    # Evidence: docs/RISK_REGISTER.md#r5-coverage-edge; UNDERSTANDING.md §2
    # Verdict: PENDING (awaiting a run against LIVE Delhi data; fixture runs are not the verdict)
    market = session.get(Market, market_id)
    market_name = market.canonical_name if market else f"market#{market_id}"
    n_days = (end - start).days + 1
    all_days = {start + timedelta(days=i) for i in range(n_days)}

    rows = list(
        session.scalars(
            select(PriceObservation).where(
                PriceObservation.market_id == market_id,
                PriceObservation.source_class == SourceClass.executed_summary,
            )
        )
    )

    reported: dict[int, set[date]] = defaultdict(set)
    same_day: dict[int, set[date]] = defaultdict(set)
    lag_hist: dict[int, int] = defaultdict(int)
    implausible = 0
    commodity_names: dict[int, str] = {}

    for r in rows:
        obs_day = to_ist(r.observed_at).date()
        if obs_day not in all_days:
            continue
        reported[r.commodity_id].add(obs_day)
        capture_day = to_ist(r.created_at).date()
        lag = (capture_day - obs_day).days
        lag_hist[lag] += 1
        if lag <= 0:
            same_day[r.commodity_id].add(obs_day)
        if r.canonical_price_paise_per_kg is None or not (
            0 < r.canonical_price_paise_per_kg <= sanity_max_paise_per_kg
        ):
            implausible += 1

    tracked = set(reported)
    for cid in tracked:
        if cid not in commodity_names:
            c = session.get(Commodity, cid)
            commodity_names[cid] = c.canonical_name if c else f"commodity#{cid}"

    expected = len(tracked) * n_days
    reported_cd = sum(len(days) for days in reported.values())
    same_day_cd = sum(len(days) for days in same_day.values())

    per_commodity = {
        commodity_names[cid]: (len(days) / n_days if n_days else 0.0)
        for cid, days in sorted(reported.items(), key=lambda kv: commodity_names[kv[0]])
    }

    return CoverageReport(
        market=market_name,
        start=start,
        end=end,
        n_days=n_days,
        tracked_commodities=len(tracked),
        expected_commodity_days=expected,
        reported_commodity_days=reported_cd,
        same_day_commodity_days=same_day_cd,
        implausible_values=implausible,
        lag_histogram=dict(sorted(lag_hist.items())),
        per_commodity=per_commodity,
    )


def r5_verdict(report: CoverageReport, *, is_live: bool) -> str:
    """The R5 verdict string. Only a LIVE run produces a real verdict."""
    prefix = "" if is_live else "[FIXTURE DATA — NOT THE REAL VERDICT] "
    if report.same_day_coverage_pct > SAME_DAY_EDGE_THRESHOLD:
        return (
            f"{prefix}NO COVERAGE EDGE: same-day coverage "
            f"{report.same_day_coverage_pct:.1%} > 90%. Agmarknet already reports Delhi "
            f"well; only intraday timing remains as a possible edge."
        )
    gap = 1.0 - report.same_day_coverage_pct
    return (
        f"{prefix}COVERAGE GAP OF {gap:.1%}: same-day coverage "
        f"{report.same_day_coverage_pct:.1%} (all-lag {report.coverage_pct:.1%}). "
        f"A coverage/timeliness edge is plausible — confirm on the full window."
    )


def format_report(report: CoverageReport, *, is_live: bool) -> str:
    lines = [
        f"Agmarknet coverage study — {report.market}",
        f"  window: {report.start} .. {report.end}  ({report.n_days} days)",
        f"  commodities tracked: {report.tracked_commodities}",
        f"  expected commodity-days: {report.expected_commodity_days}",
        f"  reported: {report.reported_commodity_days}  (coverage {report.coverage_pct:.1%})",
        f"  same-day: {report.same_day_commodity_days}  "
        f"(same-day coverage {report.same_day_coverage_pct:.1%})",
        f"  implausible values: {report.implausible_values}",
        f"  reporting-lag histogram (days->count): {report.lag_histogram}",
        "  per-commodity coverage:",
    ]
    for name, pct in report.per_commodity.items():
        lines.append(f"    {name:<20} {pct:.1%}")
    lines.append("")
    lines.append(f"  VERDICT (R5): {r5_verdict(report, is_live=is_live)}")
    return "\n".join(lines)
