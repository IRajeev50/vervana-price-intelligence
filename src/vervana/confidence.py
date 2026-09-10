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
    base = SOURCE_RELIABILITY.get(obs.source_class, 0.5)
    conv = float(obs.unit_conversion_confidence) if obs.unit_conversion_confidence else 1.0
    agreement = 1.0  # TODO(§5.4): cross-source agreement, within comparable classes only
    return round(base * conv * agreement, 2)
