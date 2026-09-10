"""Confidence scoring (§5.4), shared by the web and the digest.

price_confidence = source reliability × extraction/conversion confidence × cross-source
agreement. Cross-source agreement is not computed yet (it needs multiple *comparable*
sources and must respect the source-class guard), so it is held at 1.0 and the score is
labelled as partial wherever shown — we do not pretend to a confidence we haven't earned.
"""

from __future__ import annotations

from vervana.db.base import SourceClass

SOURCE_RELIABILITY = {
    SourceClass.executed_trade: 0.95,
    SourceClass.executed_summary: 0.80,
    SourceClass.retail_offer: 0.70,
    SourceClass.quote_indicative: 0.50,
}


def price_confidence(obs) -> float:
    """Fast composite (no DB): source reliability × conversion confidence. Used in list
    views; the evidence page uses `price_confidence_full` which adds cross-source
    agreement."""
    base = SOURCE_RELIABILITY.get(obs.source_class, 0.5)
    conv = float(obs.unit_conversion_confidence) if obs.unit_conversion_confidence else 1.0
    return round(base * conv, 2)


def _comparable_value(obs) -> float | None:
    """The value used for agreement, in comparable units: canonical ₹/kg if present, else
    the range midpoint (paise). Kept within one source class by the caller."""
    if obs.canonical_price_paise_per_kg is not None:
        return float(obs.canonical_price_paise_per_kg)
    if obs.price_low_paise is not None and obs.price_high_paise is not None:
        return (obs.price_low_paise + obs.price_high_paise) / 2
    return None


def agreement_factor(session, obs) -> tuple[float, str]:
    """Cross-source AGREEMENT (§5.4): how close this observation is to its peers of the
    SAME source class, same commodity, same day. Comparing only within a class respects
    the source-class guard (we never measure a retail offer's agreement against wholesale).
    No peers ⇒ 1.0 (we cannot assess agreement, so we don't penalise it)."""
    from sqlalchemy import select

    from vervana.models.observations import PriceObservation
    from vervana.time import to_ist

    val = _comparable_value(obs)
    if val is None or val <= 0:
        return 1.0, "no comparable value"
    obs_day = to_ist(obs.observed_at).date()
    peers = []
    for p in session.scalars(
        select(PriceObservation).where(
            PriceObservation.commodity_id == obs.commodity_id,
            PriceObservation.source_class == obs.source_class,
            PriceObservation.id != obs.id,
        )
    ):
        if to_ist(p.observed_at).date() != obs_day:
            continue
        pv = _comparable_value(p)
        if pv is not None and pv > 0:
            peers.append(pv)
    if not peers:
        return 1.0, "no same-class peers on this day"
    peers.sort()
    median = peers[len(peers) // 2]
    if median <= 0:
        return 1.0, "peer median zero"
    deviation = abs(val - median) / median
    factor = max(0.4, 1 - min(deviation, 0.6))
    return round(factor, 2), f"{len(peers)} peer(s), {deviation:.0%} from peer median"


def price_confidence_full(session, obs) -> tuple[float, str]:
    """Full §5.4 composite: source reliability × conversion confidence × cross-source
    agreement. Returns (score, agreement basis)."""
    base = SOURCE_RELIABILITY.get(obs.source_class, 0.5)
    conv = float(obs.unit_conversion_confidence) if obs.unit_conversion_confidence else 1.0
    agree, basis = agreement_factor(session, obs)
    return round(base * conv * agree, 2), basis
