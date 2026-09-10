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
