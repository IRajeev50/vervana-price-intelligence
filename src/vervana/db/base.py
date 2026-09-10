"""SQLAlchemy declarative base and custom column types.

Two custom types push the project's non-negotiable policies down to the storage
boundary, so they hold no matter which code path writes a row:

  * `UTCDateTime` rejects naive datetimes and stores/returns tz-aware UTC.
  * money is stored as integer paise in plain BigInteger columns (never float).

Enums use `enum_column` (SQLAlchemy `Enum` with `native_enum=False`), which renders
as `VARCHAR + CHECK` on both PostgreSQL and SQLite. This keeps the four source
classes constrained on every engine while avoiding PostgreSQL native-ENUM migration
friction, and returns real enum instances on read.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, TypeDecorator
from sqlalchemy.orm import DeclarativeBase

from vervana.time import ensure_aware, to_utc


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def enum_column(py_enum: type[enum.Enum]) -> Enum:
    """A portable enum column: VARCHAR + CHECK on both SQLite and PostgreSQL.

    `native_enum=False` avoids PostgreSQL native-ENUM migration friction while still
    constraining the column to the allowed values on every engine, and returns real
    enum instances on read (so comparisons and `.value` work). Values, not member
    names, are stored (they coincide here, but this is explicit and future-proof).
    """
    return Enum(
        py_enum,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )


class UTCDateTime(TypeDecorator):
    """A DateTime that refuses naive values and normalises to UTC.

    Enforces Part 7 ("store UTC, no naive datetimes in the DB") regardless of the
    underlying engine. SQLite has no native tz, so we attach UTC on the way out.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        # Rejects naive datetimes loudly rather than guessing a zone.
        return to_utc(ensure_aware(value))

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        # SQLite may hand back a naive datetime; it is UTC by construction here.
        return to_utc(value) if value.tzinfo else value.replace(tzinfo=__import__("datetime").UTC)


class SourceClass(enum.StrEnum):
    """The four price source classes. Never collapsed or coerced into one another.

    Ordering here is semantic, not a ranking:
      * quote_indicative  — a quoted range, e.g. an "aadat"/mandi quote or a video quote.
      * executed_summary  — a summary of executed trades (e.g. Agmarknet daily modal).
      * executed_trade    — an individual executed transaction (e.g. an eNAM lot).
      * retail_offer      — a consumer shelf/app price (e.g. a quick-commerce listing).
    """

    quote_indicative = "quote_indicative"
    executed_summary = "executed_summary"
    executed_trade = "executed_trade"
    retail_offer = "retail_offer"


class TimeBasis(enum.StrEnum):
    """How trustworthy a row's timestamp is. An estimate must never look exact."""

    exact = "exact"
    estimated_window = "estimated_window"
    single_daily_quote = "single_daily_quote"
    daily_summary = "daily_summary"


class CanonicalType(enum.StrEnum):
    """What an alias resolves to (polymorphic pointer target)."""

    commodity = "commodity"
    variety = "variety"
    grade = "grade"
    market = "market"


class AliasSourceType(enum.StrEnum):
    """Where an alias came from — drives trust and review priority."""

    agmarknet_official = "agmarknet_official"
    hindi_spoken = "hindi_spoken"
    hinglish_transliteration = "hinglish_transliteration"
    qcomm_sku_title = "qcomm_sku_title"
    trader_colloquial = "trader_colloquial"


class ReviewStatus(enum.StrEnum):
    """State of an alias in the human review queue."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
