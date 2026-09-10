"""Ground-truth study (M5, §5.2).

The reference is **trader invoices**, not Agmarknet (R4). For each comparator source we
compute the median absolute percentage deviation (MAPD) from the reference, per commodity.

Two modes, same machinery:
  * REAL (invoices present): MAPD(video vs invoices) and MAPD(agmarknet vs invoices). If the
    video MAPD exceeds 10%, video quotes are a sentiment signal, not a price (R3), and the
    intraday-price thesis fails.
  * INTERIM (no invoices yet): there is no reference, so we fall back to a *comparator-vs-
    comparator* ballpark check — video (Delhi) vs Agmarknet (national median). This is
    explicitly NOT the verdict (validating noise against noise identifies nothing — R4);
    it only shows whether the video quotes are in the right order of magnitude.

Additional ground-truth sources plug in by adding to `comparators` / swapping `reference`.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass
from vervana.models.entities import Commodity, Market
from vervana.models.invoice import Invoice
from vervana.models.observations import PriceObservation
from vervana.time import to_ist

VIDEO_MARKETS = ("Azadpur", "Keshopur")
R3_THRESHOLD = 0.10  # >10% median deviation => video is sentiment, not price


@dataclass
class PricePoint:
    commodity: str
    on_date: date
    paise_per_kg: float


@dataclass
class CommodityDeviation:
    commodity: str
    n_matched: int
    mapd: float  # median absolute percentage deviation


@dataclass
class StudyResult:
    mode: str  # "real" or "interim"
    reference_name: str
    comparator_name: str
    per_commodity: list[CommodityDeviation] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    @property
    def overall_mapd(self) -> float | None:
        vals = [c.mapd for c in self.per_commodity if c.n_matched]
        return statistics.median(vals) if vals else None


# --- comparator/reference extraction --------------------------------------------------
def _median_by_commodity_date(points: list[PricePoint]) -> dict[tuple[str, date], float]:
    grouped: dict[tuple[str, date], list[float]] = defaultdict(list)
    for p in points:
        grouped[(p.commodity, p.on_date)].append(p.paise_per_kg)
    return {k: statistics.median(v) for k, v in grouped.items()}


def video_points(session: Session, *, apply_units: bool = True) -> list[PricePoint]:
    """Video quote midpoints at the Delhi markets, converted to ₹/kg using the inferred
    per-commodity unit (R13 midpoint + inferred unit). Commodities whose unit can't be
    inferred are dropped when apply_units is True, rather than compared in the wrong unit."""
    from vervana.analytics.unit_inference import infer_units

    market_ids = [
        m.id
        for m in session.scalars(select(Market).where(Market.canonical_name.in_(VIDEO_MARKETS)))
    ]
    if not market_ids:
        return []
    units = infer_units(session) if apply_units else {}
    rows = session.scalars(
        select(PriceObservation).where(
            PriceObservation.source_class == SourceClass.quote_indicative,
            PriceObservation.market_id.in_(market_ids),
        )
    )
    out = []
    for r in rows:
        c = session.get(Commodity, r.commodity_id)
        mid = (r.price_low_paise + r.price_high_paise) / 2  # R13 midpoint
        if apply_units:
            u = units.get(c.canonical_name)
            if u is None or u.scale_to_kg is None:
                continue  # unit unknown -> don't compare in the wrong unit
            mid *= u.scale_to_kg
        out.append(PricePoint(c.canonical_name, to_ist(r.observed_at).date(), mid))
    return out


def agmarknet_points(session: Session) -> list[PricePoint]:
    """Agmarknet executed_summary canonical ₹/kg (national — R4/R5: not Delhi)."""
    rows = session.scalars(
        select(PriceObservation).where(
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
    )
    out = []
    for r in rows:
        c = session.get(Commodity, r.commodity_id)
        out.append(
            PricePoint(
                c.canonical_name,
                to_ist(r.observed_at).date(),
                float(r.canonical_price_paise_per_kg),
            )
        )
    return out


def invoice_points(session: Session) -> list[PricePoint]:
    rows = session.scalars(select(Invoice))
    out = []
    for r in rows:
        c = session.get(Commodity, r.commodity_id)
        out.append(PricePoint(c.canonical_name, r.invoice_date, float(r.price_paise_per_kg)))
    return out


def _deviation(
    reference: list[PricePoint], comparator: list[PricePoint]
) -> list[CommodityDeviation]:
    ref = _median_by_commodity_date(reference)
    comp = _median_by_commodity_date(comparator)
    by_commodity: dict[str, list[float]] = defaultdict(list)
    for (commodity, day), ref_val in ref.items():
        if ref_val <= 0:
            continue
        comp_val = comp.get((commodity, day))
        if comp_val is None:
            continue
        by_commodity[commodity].append(abs(comp_val - ref_val) / ref_val)
    return [
        CommodityDeviation(commodity=c, n_matched=len(v), mapd=statistics.median(v))
        for c, v in sorted(by_commodity.items())
        if v
    ]


def _level_deviation(
    reference: list[PricePoint], comparator: list[PricePoint]
) -> list[CommodityDeviation]:
    """Date-AGNOSTIC fallback: compare typical (median) level per commodity. Much weaker
    than a date-matched comparison — used only when there is no date overlap."""
    ref: dict[str, list[float]] = defaultdict(list)
    comp: dict[str, list[float]] = defaultdict(list)
    for p in reference:
        ref[p.commodity].append(p.paise_per_kg)
    for p in comparator:
        comp[p.commodity].append(p.paise_per_kg)
    out = []
    for c in sorted(set(ref) & set(comp)):
        r = statistics.median(ref[c])
        v = statistics.median(comp[c])
        if r > 0:
            out.append(
                CommodityDeviation(
                    commodity=c, n_matched=min(len(ref[c]), len(comp[c])), mapd=abs(v - r) / r
                )
            )
    return out


def run_study(session: Session) -> StudyResult:
    # RISK[R4-WEAK-GROUND-TRUTH]: The reference MUST be trader invoices, never Agmarknet —
    # DMI disclaims its own data and markets go unreported, so validating video against
    # Agmarknet is validating noise against noise. When invoices are absent this study runs
    # in INTERIM mode and refuses to issue a verdict; it only reports a ballpark check.
    # Evidence: docs/RISK_REGISTER.md#r4-weak-ground-truth; §5.2
    # Verdict: PENDING — no trader invoices supplied yet.
    invoices = invoice_points(session)
    video = video_points(session)
    agmarknet = agmarknet_points(session)

    if invoices:
        result = StudyResult(mode="real", reference_name="trader_invoices", comparator_name="video")
        result.per_commodity = _deviation(invoices, video)
        result.caveats.append("Reference = trader invoices. Agmarknet is a third comparator only.")
        return result

    # INTERIM: no invoices — video vs Agmarknet national, explicitly NOT a verdict.
    result = StudyResult(
        mode="interim", reference_name="agmarknet_national (PROXY)", comparator_name="video"
    )
    matched = _deviation(agmarknet, video)
    if matched:
        result.per_commodity = matched
        basis = "date-matched (video Delhi vs Agmarknet national, same day)"
    else:
        result.per_commodity = _level_deviation(agmarknet, video)
        basis = "LEVEL only (date-agnostic: typical video level vs typical Agmarknet level)"
    result.caveats = [
        "NO TRADER INVOICES YET — this is NOT the ground-truth verdict.",
        f"Comparison basis: {basis}.",
        "Agmarknet is used as a PROXY reference (R4: it is not ground truth).",
        "Agmarknet is national; video is Delhi (Azadpur/Keshopur) — a cross-market mismatch.",
        "Video unit is unstated; its midpoint is ASSUMED to be ₹/kg (R13).",
        "Supply invoices to upgrade this to a real, date-matched, per-commodity verdict.",
    ]
    return result


def import_invoices_csv(session: Session, path) -> dict:
    """Load trader invoices (the ground-truth reference). Columns: commodity, market,
    date, price_rupees_per_kg, trader, source_ref, notes."""
    import csv
    from datetime import datetime
    from pathlib import Path

    from vervana.db.base import CanonicalType
    from vervana.money import rupees_to_paise
    from vervana.repository.registry import resolve_by_name

    added = rejected = 0
    with Path(path).open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            low = {str(k).strip().lower(): (v or "").strip() for k, v in rec.items()}
            cid = resolve_by_name(
                session, name=low.get("commodity", ""), canonical_type=CanonicalType.commodity
            )
            if cid is None:
                rejected += 1
                continue
            mid = None
            if low.get("market"):
                mid = resolve_by_name(
                    session, name=low["market"], canonical_type=CanonicalType.market
                )
            try:
                d = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        d = datetime.strptime(low["date"], fmt).date()
                        break
                    except ValueError:
                        continue
                price = rupees_to_paise(low["price_rupees_per_kg"])
            except Exception:
                rejected += 1
                continue
            if d is None:
                rejected += 1
                continue
            session.add(
                Invoice(
                    commodity_id=cid,
                    market_id=mid,
                    invoice_date=d,
                    price_paise_per_kg=price,
                    trader=low.get("trader") or None,
                    source_ref=low.get("source_ref") or None,
                    notes=low.get("notes") or None,
                )
            )
            added += 1
    session.flush()
    return {"added": added, "rejected": rejected}


def r3_verdict(result: StudyResult) -> str:
    """R3 verdict — only issued in REAL mode."""
    if result.mode != "real":
        return (
            "R3 PENDING — interim run only (no invoices). Video quotes are treated as a "
            "quote/sentiment signal, never an executed price, until validated against invoices."
        )
    m = result.overall_mapd
    if m is None:
        return "R3 PENDING — invoices present but no overlapping commodity/date with video."
    if m > R3_THRESHOLD:
        return (
            f"R3 FAILS: median video-vs-invoice deviation {m:.1%} > 10%. Video quotes are a "
            f"SENTIMENT signal, not a price — the intraday-price thesis does not hold."
        )
    return (
        f"R3 HOLDS: median video-vs-invoice deviation {m:.1%} ≤ 10%. Video quotes track "
        f"executed prices closely enough to use as a price signal."
    )


def format_report(result: StudyResult) -> str:
    lines = [f"Ground-truth study — mode: {result.mode.upper()}"]
    lines.append(f"  reference: {result.reference_name}  ·  comparator: {result.comparator_name}")
    lines.append("")
    if result.per_commodity:
        lines.append(f"  {'commodity':<18}{'matched days':>13}{'median abs % dev':>20}")
        for c in result.per_commodity:
            lines.append(f"  {c.commodity:<18}{c.n_matched:>13}{c.mapd:>19.1%}")
        m = result.overall_mapd
        lines.append(f"\n  overall median deviation: {m:.1%}" if m is not None else "")
    else:
        lines.append("  (no overlapping commodity/date points to compare)")
    lines.append("")
    for c in result.caveats:
        lines.append(f"  ⚠ {c}")
    lines.append("")
    lines.append(f"  {r3_verdict(result)}")
    return "\n".join(lines)
