"""Per-commodity unit inference for the video corpus.

Video quotes state no unit, so canonical ₹/kg is NULL. The interim ground-truth run
exposed why this matters: some commodities are quoted per-kg (Onion ~₹40) and others per
quintal (Tomato "1500–1600" = ₹/quintal). This module infers, per commodity, whether the
video quotes are ₹/kg or ₹/quintal, and the scale factor to bring them to ₹/kg.

Inference is by ORDER OF MAGNITUDE only (a ~100× question — kg vs quintal), so using
Agmarknet's national median as the yardstick here is defensible even though Agmarknet is
NOT a price ground truth (R4): we are inferring the unit, not validating the price. Where
no Agmarknet reference exists we fall back to plausibility bounds. The result is always
flagged low/medium confidence and never mutates a stored row — callers apply the scale on
read, keeping observations immutable.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass
from vervana.models.entities import Commodity, Market
from vervana.models.observations import PriceObservation

VIDEO_MARKETS = ("Azadpur", "Keshopur")
# A fresh-produce ₹/kg above this is implausible → the quote is almost certainly ₹/quintal.
KG_PLAUSIBLE_MAX_RUPEES = 400.0


@dataclass
class InferredUnit:
    commodity: str
    inferred_unit: str  # "kg" | "quintal" | "unknown"
    scale_to_kg: float | None  # multiply a paise midpoint by this to get paise/kg
    confidence: float
    basis: str
    video_median_rupees: float
    agmarknet_median_rupees: float | None


def _video_medians(session: Session) -> dict[str, float]:
    market_ids = [
        m.id
        for m in session.scalars(select(Market).where(Market.canonical_name.in_(VIDEO_MARKETS)))
    ]
    grouped: dict[str, list[float]] = defaultdict(list)
    if not market_ids:
        return {}
    for r in session.scalars(
        select(PriceObservation).where(
            PriceObservation.source_class == SourceClass.quote_indicative,
            PriceObservation.market_id.in_(market_ids),
        )
    ):
        c = session.get(Commodity, r.commodity_id).canonical_name
        grouped[c].append((r.price_low_paise + r.price_high_paise) / 2)
    return {c: statistics.median(v) for c, v in grouped.items()}


def _agmarknet_medians(session: Session) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for r in session.scalars(
        select(PriceObservation).where(
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
    ):
        c = session.get(Commodity, r.commodity_id).canonical_name
        grouped[c].append(float(r.canonical_price_paise_per_kg))
    return {c: statistics.median(v) for c, v in grouped.items()}


def infer_units(session: Session) -> dict[str, InferredUnit]:
    video = _video_medians(session)
    agmarknet = _agmarknet_medians(session)
    out: dict[str, InferredUnit] = {}
    for commodity, vmed in video.items():
        amed = agmarknet.get(commodity)
        v_rupees = vmed / 100
        a_rupees = amed / 100 if amed else None
        if amed and amed > 0:
            ratio = vmed / amed
            # Only accept a unit when the ratio is UNAMBIGUOUSLY ~1× (kg) or ~100× (quintal).
            # A ratio in between (e.g. 3–60×) is most likely a per-CRATE/pallı quote, which
            # this kg-vs-quintal test cannot resolve — leave it "unknown" rather than force a
            # wrong ÷100 that yields nonsense like ₹5/kg potato.
            if 60 <= ratio <= 160:
                conf = max(0.5, 1 - abs(ratio - 100) / 100)
                out[commodity] = InferredUnit(
                    commodity,
                    "quintal",
                    1 / 100,
                    round(min(conf, 0.9), 2),
                    f"ratio {ratio:.0f}× Agmarknet ⇒ quintal",
                    v_rupees,
                    a_rupees,
                )
            elif 0.3 <= ratio <= 3:
                conf = max(0.5, 1 - abs(ratio - 1) / 2)
                out[commodity] = InferredUnit(
                    commodity,
                    "kg",
                    1.0,
                    round(min(conf, 0.9), 2),
                    f"ratio {ratio:.1f}× Agmarknet ⇒ kg",
                    v_rupees,
                    a_rupees,
                )
            else:
                hint = "per-crate suspected" if 3 < ratio < 60 else "ambiguous"
                out[commodity] = InferredUnit(
                    commodity,
                    "unknown",
                    None,
                    0.2,
                    f"ratio {ratio:.1f}× Agmarknet ⇒ {hint}",
                    v_rupees,
                    a_rupees,
                )
        else:
            # No Agmarknet reference: plausibility bounds.
            if v_rupees > KG_PLAUSIBLE_MAX_RUPEES:
                out[commodity] = InferredUnit(
                    commodity,
                    "quintal",
                    1 / 100,
                    0.4,
                    f"₹{v_rupees:.0f}/kg implausible ⇒ quintal",
                    v_rupees,
                    None,
                )
            else:
                out[commodity] = InferredUnit(
                    commodity, "kg", 1.0, 0.4, f"₹{v_rupees:.0f}/kg plausible ⇒ kg", v_rupees, None
                )
    return out


def format_units(units: dict[str, InferredUnit]) -> str:
    lines = ["Video-quote unit inference (per commodity)"]
    lines.append(f"  {'commodity':<16}{'unit':>9}{'→kg×':>8}{'conf':>7}   basis")
    for u in sorted(units.values(), key=lambda x: x.commodity):
        scale = "—" if u.scale_to_kg is None else f"{u.scale_to_kg:g}"
        lines.append(
            f"  {u.commodity:<16}{u.inferred_unit:>9}{scale:>8}{u.confidence:>7}   {u.basis}"
        )
    return "\n".join(lines)
