"""Assemble, format and store an intelligence report for one commodity (M9)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.intelligence.chain import ChainStep, build_chain, report_verdict
from vervana.intelligence.crops import Horizon, forecast_horizon, get_profile
from vervana.intelligence.signals import (
    STEP_SIGNALS,
    Signal,
    SignalStatus,
    collect_signals,
    load_fixture_signals,
    merge_signals,
)
from vervana.time import now_utc

ALL_KINDS = sorted({k for kinds in STEP_SIGNALS.values() for k in kinds})


@dataclass
class IntelligenceReport:
    commodity: str
    made_at_utc: str
    horizon: Horizon
    verdict: str
    verdict_reason: str
    n_observed: int
    n_simulated: int
    n_missing: int
    confidence: float
    steps: list[ChainStep]
    signals: list[Signal]
    price_context: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def build_report(
    session: Session,
    commodity: str,
    *,
    include_simulated: bool = True,
    as_of: date | None = None,
) -> IntelligenceReport:
    """Build the full signal-to-impact report for a commodity.

    Observed signals come from the context_signal store. When `include_simulated`
    is set (dev default), the bundled fixture fills gaps - always labelled
    simulated, never blended with an observed feed of the same kind.
    """
    del as_of  # reserved for walk-forward evaluation of the chain itself
    profile = get_profile(commodity)
    horizon = forecast_horizon(profile)
    observed = collect_signals(session, ALL_KINDS)
    simulated = load_fixture_signals() if include_simulated else []
    merged = merge_signals(observed, simulated, required_kinds=ALL_KINDS)
    steps = build_chain(merged)
    verdict, verdict_reason = report_verdict(steps)
    n_obs = sum(1 for s in merged if s.status == SignalStatus.observed)
    n_sim = sum(1 for s in merged if s.status == SignalStatus.simulated)
    n_miss = sum(1 for s in merged if s.status == SignalStatus.missing)
    confidence = min((s.confidence for s in steps if s.confidence > 0), default=0.0)

    # Price context: does the platform hold price observations for this commodity?
    from vervana.models.entities import Commodity
    from vervana.models.observations import PriceObservation

    price_context: dict = {"observations": 0, "latest_canonical_rupees": None, "latest_class": None}
    c = session.scalar(select(Commodity).where(Commodity.canonical_name == commodity))
    if c is not None:
        rows = list(
            session.scalars(
                select(PriceObservation)
                .where(PriceObservation.commodity_id == c.id)
                .order_by(PriceObservation.observed_at.desc())
                .limit(1)
            )
        )
        from sqlalchemy import func

        n = session.scalar(
            select(func.count())
            .select_from(PriceObservation)
            .where(PriceObservation.commodity_id == c.id)
        )
        if rows:
            o = rows[0]
            price_context = {
                "observations": n or 0,
                "latest_canonical_rupees": (
                    None
                    if o.canonical_price_paise_per_kg is None
                    else round(o.canonical_price_paise_per_kg / 100, 2)
                ),
                "latest_class": o.source_class.value,
                "latest_obs_id": o.id,
            }

    return IntelligenceReport(
        commodity=commodity,
        made_at_utc=now_utc().isoformat(),
        horizon=horizon,
        verdict=verdict,
        verdict_reason=verdict_reason,
        n_observed=n_obs,
        n_simulated=n_sim,
        n_missing=n_miss,
        confidence=round(confidence, 2),
        steps=steps,
        signals=merged,
        price_context=price_context,
    )


def format_report(report: IntelligenceReport) -> str:
    lines = [
        f"INTELLIGENCE OUTLOOK - {report.commodity}",
        f"made at (UTC): {report.made_at_utc}",
        f"honest horizon: {report.horizon.label} ({report.horizon.basis})",
        f"verdict: {report.verdict} - {report.verdict_reason}",
        f"inputs: {report.n_observed} observed, {report.n_simulated} simulated, "
        f"{report.n_missing} missing · confidence {report.confidence:.2f}",
        "",
        "Reasoning chain:",
    ]
    for s in report.steps:
        lines.append(f"  [{s.status:<22}] {s.name}: {s.finding} (conf {s.confidence:.2f})")
        for m in s.missing:
            lines.append(f"      missing input: {m}")
    lines.append("")
    lines.append("Signals:")
    for sig in report.signals:
        lines.append(f"  - {sig.describe()}")
    if report.price_context.get("latest_canonical_rupees") is not None:
        lines.append("")
        lines.append(
            f"Price context: latest {report.price_context['latest_class']} "
            f"Rs {report.price_context['latest_canonical_rupees']}/kg "
            f"(evidence #{report.price_context.get('latest_obs_id')})"
        )
    lines.append("")
    lines.append("Not trading advice. Simulated inputs are labelled and cap confidence.")
    return "\n".join(lines)


def save_record(session: Session, report: IntelligenceReport) -> int:
    """Persist the report, append-only, so every published outlook is auditable."""
    from vervana.models.intelligence import IntelligenceReportRecord

    rec = IntelligenceReportRecord(
        commodity=report.commodity,
        made_at=now_utc(),
        horizon_label=report.horizon.label,
        verdict=report.verdict,
        n_observed=report.n_observed,
        n_simulated=report.n_simulated,
        n_missing=report.n_missing,
        confidence=report.confidence,
        report_json=json.dumps(report.to_dict(), default=str),
    )
    session.add(rec)
    session.flush()
    return rec.id
