"""Unit-conversion lookup. Returns the most specific matching convention, or None.

None means we do not know the weight for this (market, commodity, unit) — the caller
must leave the canonical ₹/kg price NULL rather than guess (Part 3.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.models.units import UnitConvention


@dataclass
class Conversion:
    kg_equivalent: float
    confidence: float
    source: str


def lookup_kg_equivalent(
    session: Session,
    *,
    unit_raw: str,
    commodity_id: int | None = None,
    market_id: int | None = None,
    on_date: date | None = None,
) -> Conversion | None:
    """Most specific match wins: (market+commodity) > commodity > market > global."""
    candidates = list(
        session.scalars(select(UnitConvention).where(UnitConvention.unit_raw == unit_raw))
    )
    if on_date is not None:
        candidates = [c for c in candidates if _effective(c, on_date)]

    def specificity(c: UnitConvention) -> int:
        return (c.market_id is not None) * 2 + (c.commodity_id is not None)

    def matches(c: UnitConvention) -> bool:
        if c.market_id is not None and c.market_id != market_id:
            return False
        if c.commodity_id is not None and c.commodity_id != commodity_id:
            return False
        return True

    viable = [c for c in candidates if matches(c)]
    if not viable:
        return None
    best = max(viable, key=specificity)
    return Conversion(
        kg_equivalent=float(best.kg_equivalent),
        confidence=float(best.confidence),
        source=best.source,
    )


def _effective(c: UnitConvention, on: date) -> bool:
    if c.effective_from and on < c.effective_from:
        return False
    return not (c.effective_to and on > c.effective_to)
