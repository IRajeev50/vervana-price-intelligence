"""Entity registry: commodity, variety, grade, market, alias.

This is the most valuable component in the system, and per R9 the *only* one with
a colourable IP claim — not because it holds prices (prices are facts, unprotected
under Eastern Book Company v. D.B. Modak), but because the alias resolution and its
human verification embody editorial judgment. The registry is therefore treated
as the asset: its verification workflow, not the raw price data, is what a data room
could defend.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vervana.db.base import AliasSourceType, Base, CanonicalType, UTCDateTime, enum_column

# RISK[R9-NOT-IP]: This registry is treated as proprietary IP. Under Eastern Book
# Company v. D.B. Modak (SC of India, 2008) India applies a "modicum of creativity"
# test and does NOT protect bare factual compilations. Commodity/variety/market names
# and prices are facts; only the *editorial judgment* in alias resolution + human
# verification (the alias/alias_review tables below) could attract protection. If the
# product's defensibility is pitched on "we own the price dataset", that claim fails;
# the defensible surface is this verification work and nothing else.
# Evidence: docs/RISK_REGISTER.md#r9-not-ip; UNDERSTANDING.md §3.1
# Verdict: PENDING


class Commodity(Base):
    __tablename__ = "commodity"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(120), unique=True)
    agmarknet_commodity_code: Mapped[str | None] = mapped_column(String(32), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    varieties: Mapped[list[Variety]] = relationship(back_populates="commodity")


class Variety(Base):
    __tablename__ = "variety"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodity.id"))
    canonical_name: Mapped[str] = mapped_column(String(120))
    agmarknet_variety_code: Mapped[str | None] = mapped_column(String(32), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    commodity: Mapped[Commodity] = relationship(back_populates="varieties")

    __table_args__ = (Index("ix_variety_commodity", "commodity_id"),)


class Grade(Base):
    __tablename__ = "grade"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity_id: Mapped[int | None] = mapped_column(ForeignKey("commodity.id"), default=None)
    canonical_name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class Market(Base):
    __tablename__ = "market"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(160), unique=True)
    apmc_name: Mapped[str | None] = mapped_column(String(160), default=None)
    city: Mapped[str | None] = mapped_column(String(80), default=None)
    state: Mapped[str | None] = mapped_column(String(80), default=None)
    agmarknet_market_code: Mapped[str | None] = mapped_column(String(32), default=None)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), default=None)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), default=None)


class Alias(Base):
    """A spoken/written/typed form that resolves to one canonical entity.

    Many-to-many by design (Part 3.2): there is NO unique constraint on alias_text.
    The same text may resolve to several canonicals (e.g. "mirchi" -> chilli or
    capsicum), each row carrying its own confidence and verification state; and one
    canonical entity has many aliases across languages and SKU titles.

    `canonical_type` + `canonical_id` is a polymorphic pointer (validated in the
    repository, since a single SQL FK cannot span four target tables).
    """

    __tablename__ = "alias"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias_text: Mapped[str] = mapped_column(String(200))
    alias_language: Mapped[str] = mapped_column(String(16))  # e.g. 'en', 'hi', 'hi-Latn'
    alias_source_type: Mapped[AliasSourceType] = mapped_column(enum_column(AliasSourceType))

    canonical_type: Mapped[CanonicalType] = mapped_column(enum_column(CanonicalType))
    canonical_id: Mapped[int] = mapped_column()

    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)

    # Verification provenance. An automated match is unverified until a recorded
    # reviewer promotes it (see alias_review). verified_by/at are NULL when unverified.
    created_by: Mapped[str] = mapped_column(String(80), default="system")
    verified_by: Mapped[str | None] = mapped_column(String(80), default=None)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        Index("ix_alias_text", "alias_text"),
        Index("ix_alias_canonical", "canonical_type", "canonical_id"),
    )

    @property
    def is_verified(self) -> bool:
        return self.verified_by is not None
