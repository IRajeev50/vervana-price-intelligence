"""Build a univariate daily price series from the fact store, for forecasting."""

from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass
from vervana.models.observations import PriceObservation
from vervana.time import to_ist


def price_series(
    session: Session,
    *,
    commodity_id: int,
    market_id: int,
    source_class: SourceClass = SourceClass.executed_summary,
) -> np.ndarray:
    """Daily canonical ₹/kg (paise) series for one commodity+market+class, oldest→newest.

    One value per day (the latest non-superseded observation that day). Superseded rows
    are excluded.
    """
    # RISK[R13-RANGE-MIDPOINT]: The modelled series uses `canonical_price_paise_per_kg`,
    # which for a ranged source is a single representative number (for Agmarknet it comes
    # from the modal price; for a quoted range it would be the midpoint). Collapsing a
    # range to one number is a modelling assumption the data model deliberately refuses to
    # make at write time — skew, thin tails, and quote-vs-trade spread all violate it. Any
    # forecast error attributable to this choice belongs here, not to the model.
    # Evidence: docs/RISK_REGISTER.md#r13-range-midpoint; UNDERSTANDING.md §3.5
    # Verdict: PENDING
    rows = list(
        session.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.commodity_id == commodity_id,
                PriceObservation.market_id == market_id,
                PriceObservation.source_class == source_class,
                PriceObservation.canonical_price_paise_per_kg.is_not(None),
            )
            .order_by(PriceObservation.observed_at)
        )
    )
    superseded = {r.supersedes_id for r in rows if r.supersedes_id is not None}
    by_day: dict[str, int] = {}
    for r in rows:
        if r.id in superseded:
            continue
        day = to_ist(r.observed_at).date().isoformat()
        by_day[day] = r.canonical_price_paise_per_kg  # later row on same day wins
    return np.array([by_day[d] for d in sorted(by_day)], dtype=float)


def quote_midpoint_series(session: Session, *, commodity_id: int, market_id: int) -> np.ndarray:
    """Daily series from quote_indicative *range midpoints*, converted to ₹/kg using the
    inferred per-commodity unit (paise), oldest→newest.

    Video quotes have no stated unit, so we apply the inferred kg/quintal scale
    (unit_inference). Where the unit can't be inferred the raw midpoint is kept — the
    series stays internally consistent (directional accuracy / sMAPE are scale-invariant),
    only absolute MAE would then not be ₹/kg. R13 midpoint assumption applies throughout.
    """
    from vervana.analytics.unit_inference import infer_units
    from vervana.models.entities import Commodity

    cname = session.get(Commodity, commodity_id).canonical_name
    u = infer_units(session).get(cname)
    scale = u.scale_to_kg if (u and u.scale_to_kg) else 1.0
    rows = list(
        session.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.commodity_id == commodity_id,
                PriceObservation.market_id == market_id,
                PriceObservation.source_class == SourceClass.quote_indicative,
            )
            .order_by(PriceObservation.observed_at)
        )
    )
    by_day: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in rows:
        day = to_ist(r.observed_at).date().isoformat()
        mid = (r.price_low_paise + r.price_high_paise) / 2 * scale  # inferred ₹/kg
        # average multiple quotes on the same day (same source class — guard-safe)
        by_day[day] = by_day.get(day, 0.0) + mid
        counts[day] = counts.get(day, 0) + 1
    return np.array([by_day[d] / counts[d] for d in sorted(by_day)], dtype=float)
