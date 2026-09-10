"""The single fact table: price_observation (Part 3.1).

Design invariants enforced here at the schema level (the repository adds the rest):
  * source_class is one of exactly four values, never coerced.
  * ranges are never collapsed at write time: price_low/price_high are primary,
    price_point is nullable and only set when the source gives one number.
  * provenance is a constraint: source_url and raw_quote must be present and non-empty.
  * unit_raw is immutable; canonical ₹/kg is derived and NULL when weight is unknown.
  * time_basis records how trustworthy observed_at is; estimates never look exact.
  * append-only: corrections insert a new row referencing supersedes_id; no in-place UPDATE.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, SourceClass, TimeBasis, UTCDateTime, enum_column


class PriceObservation(Base):
    __tablename__ = "price_observation"

    id: Mapped[int] = mapped_column(primary_key=True)

    # What was priced.
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodity.id"))
    variety_id: Mapped[int | None] = mapped_column(ForeignKey("variety.id"), default=None)
    grade_id: Mapped[int | None] = mapped_column(ForeignKey("grade.id"), default=None)
    market_id: Mapped[int] = mapped_column(ForeignKey("market.id"))

    # What KIND of price this is. Never averaged across classes (repository guard).
    source_class: Mapped[SourceClass] = mapped_column(enum_column(SourceClass))

    # Price as a range in integer paise. Ranges are primary and never collapsed.
    price_low_paise: Mapped[int] = mapped_column(BigInteger)
    price_high_paise: Mapped[int] = mapped_column(BigInteger)
    # Set ONLY when the source genuinely states a single number.
    price_point_paise: Mapped[int | None] = mapped_column(BigInteger, default=None)

    # Unit. unit_raw is immutable; canonical is derived and may be NULL (unknown weight).
    unit_raw: Mapped[str] = mapped_column(String(64))
    canonical_price_paise_per_kg: Mapped[int | None] = mapped_column(BigInteger, default=None)
    unit_kg_equivalent: Mapped[float | None] = mapped_column(Numeric(12, 4), default=None)
    unit_conversion_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), default=None)

    # Provenance — a row that cannot be traced to evidence must fail insertion.
    source_url: Mapped[str] = mapped_column(String(500))
    raw_quote: Mapped[str] = mapped_column(Text)

    # Time. observed_at is tz-aware UTC (UTCDateTime rejects naive). time_basis says
    # how much to trust it; window bounds are set for estimated_window.
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    time_basis: Mapped[TimeBasis] = mapped_column(enum_column(TimeBasis))
    observed_window_start: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    observed_window_end: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    # Observer (M7 field observers); NULL for public sources. Independence status lives
    # on the observer record (R11), not here, so it cannot be forgotten per-row.
    observer_id: Mapped[int | None] = mapped_column(default=None)

    # Append-only correction chain.
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("price_observation.id"), default=None
    )
    supersede_reason: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    __table_args__ = (
        # Ranges are ordered.
        CheckConstraint("price_low_paise <= price_high_paise", name="ck_price_range_ordered"),
        # Provenance must be present and non-empty (traceability is a constraint).
        CheckConstraint("length(trim(source_url)) > 0", name="ck_source_url_present"),
        CheckConstraint("length(trim(raw_quote)) > 0", name="ck_raw_quote_present"),
        # A point price, when present, must sit within its own range.
        CheckConstraint(
            "price_point_paise IS NULL OR "
            "(price_point_paise >= price_low_paise AND price_point_paise <= price_high_paise)",
            name="ck_point_within_range",
        ),
        Index("ix_obs_commodity_time", "commodity_id", "observed_at"),
        Index("ix_obs_market_time", "market_id", "observed_at"),
        Index("ix_obs_source_class", "source_class"),
    )
