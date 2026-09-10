"""Price repository — the sanctioned access path, and home of the source-class guard.

The guard exists because the product's credibility dies the first time it averages a
quick-commerce retail price with an Azadpur wholesale quote. Aggregation lives ONLY
here, and every aggregate:
  * requires a single, explicit source_class (there is no cross-class average);
  * excludes superseded rows (append-only means old rows still sit in the table);
  * uses canonical ₹/kg and skips rows whose unit weight is unknown (canonical NULL).

Prices are insert-only. Corrections go through `supersede()`, which inserts a new row;
there is deliberately no function that UPDATEs a price in place.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass
from vervana.models.observations import PriceObservation
from vervana.time import IST, now_utc


class MixedSourceClassError(ValueError):
    """Raised when an aggregation is asked to span more than one source_class."""


def _superseded_ids(observations: Sequence[PriceObservation]) -> set[int]:
    """IDs that some other row in the set supersedes (i.e. the old, replaced rows)."""
    return {o.supersedes_id for o in observations if o.supersedes_id is not None}


def mean_canonical_price_paise_per_kg(observations: Sequence[PriceObservation]) -> int:
    """Mean canonical ₹/kg (in paise) over observations of a SINGLE source class.

    This is the guard. Passing a set that spans classes — e.g. the result of a naive
    "all potato prices today" query — raises MixedSourceClassError rather than
    returning a meaningless blended number.
    """
    if not observations:
        raise ValueError("no observations to aggregate")

    classes = {o.source_class for o in observations}
    if len(classes) > 1:
        names = sorted(c.value if isinstance(c, SourceClass) else str(c) for c in classes)
        raise MixedSourceClassError(
            "refusing to average across source classes "
            f"{names}: a retail offer and a wholesale quote are not comparable. "
            "Aggregate within one source_class."
        )

    superseded = _superseded_ids(observations)
    live = [o for o in observations if o.id not in superseded]
    usable = [o for o in live if o.canonical_price_paise_per_kg is not None]
    if not usable:
        raise ValueError(
            "no rows with a canonical ₹/kg price to average "
            "(unknown unit weight leaves canonical price NULL — we do not guess)"
        )
    total = sum(o.canonical_price_paise_per_kg for o in usable)
    return round(total / len(usable))


def _ist_day_bounds_utc(on_date: date) -> tuple[datetime, datetime]:
    """UTC [start, end) datetimes bounding an IST calendar day."""
    start_ist = datetime(on_date.year, on_date.month, on_date.day, tzinfo=IST)
    end_ist = datetime(on_date.year, on_date.month, on_date.day, 23, 59, 59, 999999, tzinfo=IST)
    from vervana.time import to_utc

    return to_utc(start_ist), to_utc(end_ist)


def observations_for_commodity_on_date(
    session: Session, *, commodity_id: int, on_date: date
) -> list[PriceObservation]:
    """Every observation (ALL source classes) for a commodity on an IST day.

    Intentionally returns mixed classes — it is what a naive caller reaches for, and
    feeding its result to `mean_canonical_price_paise_per_kg` is exactly what the guard
    is there to reject.
    """
    start_utc, end_utc = _ist_day_bounds_utc(on_date)
    stmt = (
        select(PriceObservation)
        .where(PriceObservation.commodity_id == commodity_id)
        .where(PriceObservation.observed_at >= start_utc)
        .where(PriceObservation.observed_at <= end_utc)
    )
    return list(session.scalars(stmt))


def average_canonical_price(
    session: Session,
    *,
    commodity_id: int,
    source_class: SourceClass,
    on_date: date,
) -> int:
    """Safe average: one commodity, one source_class, one IST day, superseded excluded."""
    obs = [
        o
        for o in observations_for_commodity_on_date(
            session, commodity_id=commodity_id, on_date=on_date
        )
        if o.source_class == source_class
    ]
    return mean_canonical_price_paise_per_kg(obs)


def insert_observation(session: Session, **kwargs) -> PriceObservation:
    """Insert one observation. Schema constraints enforce provenance/ranges/etc."""
    kwargs.setdefault("created_at", now_utc())
    obs = PriceObservation(**kwargs)
    session.add(obs)
    session.flush()
    return obs


def supersede(session: Session, old_id: int, *, reason: str, **new_kwargs) -> PriceObservation:
    """Append-only correction: insert a NEW row that supersedes `old_id`.

    Never mutates the old row — the audit trail is the product.
    """
    old = session.get(PriceObservation, old_id)
    if old is None:
        raise ValueError(f"cannot supersede unknown observation id={old_id}")
    return insert_observation(session, supersedes_id=old_id, supersede_reason=reason, **new_kwargs)
