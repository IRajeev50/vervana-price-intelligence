"""NITI Aayog Aspirational Districts - programme membership, not a metric.

This layer records *which* districts the Government of India has designated
"Aspirational" under NITI Aayog's Aspirational Districts Programme (ADP,
launched January 2018, 112 districts). It is deliberately membership-only:

  * a row asserts one fact - "this state x district is on the official ADP
    list" - and nothing about performance, ranking or KPI scores;
  * the granular ADP indicator scores live behind NITI's Champions of Change
    dashboard (championsofchange.gov.in), which has no open, licensed bulk
    export. We do NOT invent those numbers. Until a real feed is connected the
    KPI layer stays empty and is labelled as such in the UI (see RISK[R14]);
  * provenance is a constraint, same creed as the price layer: source_url must
    be present and non-empty, so a row that cannot be traced to its official
    NITI source fails insertion.

The value here is the join, not the list: overlaying ADP membership onto the
district crop-production layer shows which of the districts we already hold
official production data for are Aspirational - and the programme's
Agriculture & Water Resources theme is exactly the supply angle this platform
reasons about.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class AspirationalDistrict(Base):
    __tablename__ = "aspirational_district"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Official serial number on the NITI list (1..112), kept for traceability.
    sno: Mapped[int] = mapped_column()
    state_name: Mapped[str] = mapped_column(String(60))
    district_name: Mapped[str] = mapped_column(String(80))

    # Normalised key for joining to other layers (crop production, markets).
    # Lower-cased, punctuation/whitespace stripped - stored so the join is
    # explicit and auditable rather than recomputed ad hoc at read time.
    district_key: Mapped[str] = mapped_column(String(80), index=True)

    # Provenance - a row that cannot be traced to its official source must fail.
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))

    imported_at: Mapped[datetime] = mapped_column(UTCDateTime)

    __table_args__ = (
        # One row per state x district - the official list has no duplicates.
        UniqueConstraint("state_name", "district_name", name="uq_aspirational_state_district"),
        Index("ix_aspirational_state", "state_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AspirationalDistrict {self.sno} {self.state_name}/{self.district_name}>"
