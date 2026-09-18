"""Official district crop production (DES/APY) - supply context, not price evidence.

These rows are physical production statistics published by the Directorate of
Economics & Statistics (Ministry of Agriculture), one row per
district x crop x season x year. They are deliberately kept OUT of the
price_observation fact table: production is not a price, not a mandi arrival,
and not traded volume. The layer answers "what does this district grow, and how
much of it" so commodity/corridor prioritisation rests on official data.

Design invariants (same creed as the price layer):
  * rows are stored exactly as published - never aggregated at write time;
  * provenance is a constraint: source_url must be present and non-empty;
  * DES publishes either a single season="Total" row per crop-year or per-season
    rows (Kharif/Rabi/Summer/...). The Total row, when present, already equals
    the seasonal sum, so aggregation happens only at read time (see
    vervana.repository.crop_production) and never adds Total + seasons together;
  * blank production/area in the source stays NULL here - never zero-filled.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class CropProductionRecord(Base):
    __tablename__ = "crop_production"

    id: Mapped[int] = mapped_column(primary_key=True)

    # What was grown, where, when. year_label stays the source string
    # (e.g. "2022-2023") so the row cannot be mistaken for a calendar year.
    year_label: Mapped[str] = mapped_column(String(9))
    state_name: Mapped[str] = mapped_column(String(60))
    district_name: Mapped[str] = mapped_column(String(60))
    crop_name: Mapped[str] = mapped_column(String(80))
    crop_type: Mapped[str] = mapped_column(String(40), default="")
    # Kharif / Rabi / Summer / Autumn / Winter / Whole Year / Total (see module docstring).
    season: Mapped[str] = mapped_column(String(20))

    # Physical quantities, exactly as published. NULL means the source left it blank.
    area_ha: Mapped[float | None] = mapped_column(Numeric(14, 2), default=None)
    production_t: Mapped[float | None] = mapped_column(Numeric(16, 3), default=None)
    yield_t_per_ha: Mapped[float | None] = mapped_column(Numeric(12, 4), default=None)

    # Provenance - a row that cannot be traced to its official source must fail insertion.
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))

    imported_at: Mapped[datetime] = mapped_column(UTCDateTime)

    __table_args__ = (
        # One row per district x crop x season x year, as published.
        UniqueConstraint(
            "year_label",
            "state_name",
            "district_name",
            "crop_name",
            "season",
            name="uq_crop_production_row",
        ),
        CheckConstraint("length(trim(source_url)) > 0", name="ck_cropprod_source_url_present"),
        Index("ix_cropprod_district_year", "district_name", "year_label"),
        Index("ix_cropprod_crop", "crop_name"),
    )
