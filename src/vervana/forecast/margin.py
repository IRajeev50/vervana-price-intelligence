"""Margin watch (M14): where does a price sit inside the band?

The product's decision surface. Given a quoted or executed price and the band
(p10/p50/p90) for that commodity-mandi, classify the price into an actionable
zone - never a naked number, always labelled with the band it was judged against.

Zones map the directive's "below p25 favorable / above p75 caution" onto the
p10/p50/p90 band we actually model (decision 3a): the lower/upper half is split at
p50, and the band edges (p10/p90) mark the unusual tails. Phase 4 feeds each GRN
line through this exact function.
"""

from __future__ import annotations

from dataclasses import dataclass

from vervana.forecast.band import Band


@dataclass(frozen=True)
class MarginVerdict:
    zone: str  # below-band | favorable | watch | caution
    label: str  # human one-liner with the band evidence
    price_paise: float


def _rupees(paise: float) -> str:
    return f"₹{paise / 100:.2f}/kg"


def margin_watch(price_paise: float, band: Band) -> MarginVerdict:
    """Classify `price_paise` against `band`. Boundaries are inclusive upward:
    price == p50 is 'watch' (upper half starts at the median)."""
    p = float(price_paise)
    bt = (
        f"band p10 {_rupees(band.p10)} / p50 {_rupees(band.p50)} / p90 {_rupees(band.p90)}"
    )
    px = _rupees(p)
    if p < band.p10:
        zone, note = "below-band", "BELOW the band — unusually cheap, verify"
    elif p < band.p50:
        zone, note = "favorable", "in the lower half — favorable"
    elif p <= band.p90:
        zone, note = "watch", "in the upper half — watch"
    else:
        zone, note = "caution", "ABOVE the band — caution, likely overpaying"
    return MarginVerdict(zone, f"{px} is {note} ({bt}).", p)
