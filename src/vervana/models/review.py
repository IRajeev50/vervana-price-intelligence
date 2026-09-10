"""Alias review queue (Part 3.2).

Automated matches are never trusted on their own: each enters here as `pending`, and
promotion to a verified alias requires a *recorded reviewer*. This table is the audit
trail of the editorial judgment that (per R9) is the registry's only defensible surface.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, ReviewStatus, UTCDateTime, enum_column


class AliasReview(Base):
    __tablename__ = "alias_review"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias_id: Mapped[int] = mapped_column(ForeignKey("alias.id"))
    status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus), default=ReviewStatus.pending
    )

    proposed_by: Mapped[str] = mapped_column(String(80), default="system")
    proposed_at: Mapped[datetime] = mapped_column(UTCDateTime)

    # The method + score that produced the automated suggestion, kept for auditing
    # how good the matcher was at the time of the decision.
    method: Mapped[str | None] = mapped_column(String(40), default=None)
    score: Mapped[float | None] = mapped_column(Numeric(6, 4), default=None)

    decided_by: Mapped[str | None] = mapped_column(String(80), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
