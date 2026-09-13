"""Upstream crop signals (M9): what the platform knows before the price moves.

A signal is a fact about production, supply, policy or demand upstream of the
mandi price: rainfall deficit, NDVI anomaly, reservoir level, acreage change,
arrivals, stocks, mill recovery, input sales, policy events.

Every signal is one of three statuses, and the label travels with it everywhere:
  * observed  - ingested into the context_signal store with a named source;
  * simulated - bundled sample values for development/demos (NEVER presented as
    live data; caps the confidence of every conclusion built on it);
  * missing   - required by the reasoning chain but not present. Missing is a
    first-class answer: the chain reports it instead of guessing.
"""

from __future__ import annotations

import csv
import enum
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.models.context import ContextSignal

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SUGAR_FIXTURE = REPO_ROOT / "data" / "samples" / "sugar_signals_sample.csv"


class SignalStatus(enum.StrEnum):
    observed = "observed"
    simulated = "simulated"
    missing = "missing"


# The signal kinds the chain understands, with units, so a wrong-typed feed is
# caught at import instead of silently mis-weighted.
SIGNAL_KINDS: dict[str, str] = {
    "acreage_change_pct": "% change in sown area vs last year",
    "rainfall_deficit_pct": "% rainfall vs long-period average (negative = deficit)",
    "ndvi_anomaly": "vegetation-index anomaly vs season normal (-1..1)",
    "reservoir_pct": "reservoir storage as % of capacity",
    "pest_outbreak": "pest/disease report (text severity)",
    "arrivals_change_pct": "% change in mandi arrivals vs season normal",
    "production_lmt": "production estimate, lakh metric tonnes",
    "consumption_lmt": "consumption estimate, lakh metric tonnes",
    "stocks_lmt": "closing stocks, lakh metric tonnes",
    "crushing_recovery_pct": "mill sugar recovery %",
    "input_sales_change_pct": "% change in fertilizer/pesticide sales vs normal",
    "policy_event": "government intervention (text)",
    # M11 supply-side layer (satellite / event-detection feeds):
    "sowing_progress_pct": "% of normal sown area planted by this date (event detection)",
    "harvest_progress_pct": "% of crop area harvested by this date (event detection)",
}

# Which kinds feed which chain step. A step with none of its kinds present must
# say "insufficient evidence".
STEP_SIGNALS: dict[str, list[str]] = {
    "production": [
        "acreage_change_pct",
        "rainfall_deficit_pct",
        "ndvi_anomaly",
        "reservoir_pct",
        "sowing_progress_pct",
    ],
    "supply": [
        "arrivals_change_pct",
        "stocks_lmt",
        "production_lmt",
        "crushing_recovery_pct",
        "harvest_progress_pct",
    ],
    "balance": ["production_lmt", "consumption_lmt", "stocks_lmt"],
    "impacts": ["input_sales_change_pct", "policy_event"],
}


@dataclass
class Signal:
    kind: str
    region: str
    on_date: date | None
    value_numeric: float | None
    value_text: str | None
    status: SignalStatus
    source: str
    source_url: str | None = None
    note: str = ""

    def describe(self) -> str:
        val = (
            f"{self.value_numeric:g}"
            if self.value_numeric is not None
            else (self.value_text or "?")
        )
        unit = SIGNAL_KINDS.get(self.kind, self.kind)
        return f"{self.kind} = {val} ({self.region}; {unit}; {self.status.value}: {self.source})"


def collect_signals(session: Session, kinds: list[str] | None = None) -> list[Signal]:
    """Read observed signals from the context_signal store."""
    stmt = select(ContextSignal).order_by(ContextSignal.on_date.desc())
    rows = list(session.scalars(stmt))
    out = []
    for r in rows:
        if kinds and r.signal_type not in kinds:
            continue
        out.append(
            Signal(
                kind=r.signal_type,
                region=r.region,
                on_date=r.on_date,
                value_numeric=float(r.value_numeric) if r.value_numeric is not None else None,
                value_text=r.value_text,
                status=SignalStatus.observed,
                source=r.source,
                source_url=r.source_url,
            )
        )
    return out


def load_fixture_signals(path: Path = SUGAR_FIXTURE) -> list[Signal]:
    """Load the bundled SIMULATED sample signals. Every row is labelled simulated;
    the fixture exists so the chain can be exercised without pretending live feeds
    are connected."""
    out: list[Signal] = []
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(
                Signal(
                    kind=row["signal_type"],
                    region=row["region"],
                    on_date=date.fromisoformat(row["on_date"]) if row.get("on_date") else None,
                    value_numeric=float(row["value_numeric"]) if row.get("value_numeric") else None,
                    value_text=row.get("value_text") or None,
                    status=SignalStatus.simulated,
                    source=row.get("source") or "simulated_fixture",
                    source_url=row.get("source_url") or None,
                    note=row.get("note") or "",
                )
            )
    return out


def merge_signals(
    observed: list[Signal], simulated: list[Signal], required_kinds: list[str] | None = None
) -> list[Signal]:
    """Combine observed + simulated signals, observed kind+region winning.

    Simulated rows fill gaps for development but are never upgraded: a kind that
    has any observed row drops its simulated stand-ins (no blending of real and
    pretend data). Kinds in `required_kinds` with no signal at all get an explicit
    `missing` marker so the chain can say so.
    """
    observed_keys = {(s.kind, s.region) for s in observed}
    observed_kinds = {s.kind for s in observed}
    merged = list(observed)
    for s in simulated:
        if (s.kind, s.region) in observed_keys or s.kind in observed_kinds:
            continue  # an observed feed exists for this kind; drop the stand-in
        merged.append(s)
    if required_kinds:
        present = {s.kind for s in merged}
        for kind in required_kinds:
            if kind not in present:
                merged.append(
                    Signal(
                        kind=kind,
                        region="-",
                        on_date=None,
                        value_numeric=None,
                        value_text=None,
                        status=SignalStatus.missing,
                        source="not connected",
                        note="no observed or simulated input for this signal",
                    )
                )
    return merged


def import_signals_csv(session: Session, path: Path) -> dict:
    """Import OBSERVED upstream signals into context_signal from a CSV.

    Columns: signal_type, region, on_date, value_numeric, value_text, source,
    source_url. `source` is required - an observed signal without a named source
    would be a provenance lie. Rejects unknown signal types so a mistyped feed
    cannot silently enter the chain.
    """
    added, rejected = 0, 0
    reasons: dict[str, int] = {}

    def reject(reason: str) -> None:
        nonlocal rejected
        rejected += 1
        reasons[reason] = reasons.get(reason, 0) + 1

    with Path(path).open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            kind = (row.get("signal_type") or "").strip()
            source = (row.get("source") or "").strip()
            if kind not in SIGNAL_KINDS:
                reject(f"unknown signal_type '{kind}'")
                continue
            if not source or source == "simulated_fixture":
                reject("observed signal requires a named real source")
                continue
            try:
                on_date = date.fromisoformat((row.get("on_date") or "").strip())
            except ValueError:
                reject("bad on_date")
                continue
            session.add(
                ContextSignal(
                    signal_type=kind,
                    region=(row.get("region") or "unknown").strip(),
                    on_date=on_date,
                    value_numeric=float(row["value_numeric"])
                    if (row.get("value_numeric") or "").strip()
                    else None,
                    value_text=(row.get("value_text") or "").strip() or None,
                    source=source,
                    source_url=(row.get("source_url") or "").strip() or None,
                )
            )
            added += 1
    session.flush()
    return {"added": added, "rejected": rejected, "reasons": reasons}
