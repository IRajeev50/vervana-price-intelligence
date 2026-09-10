"""Stored intelligence reports (M9): append-only, like the prospective forecast log.

Every outlook the platform publishes is stored unedited with its input counts
(observed / simulated / missing) and confidence, so the track record of the
reasoning chain can be audited exactly like the forecast log.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class IntelligenceReportRecord(Base):
    __tablename__ = "intelligence_report"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity: Mapped[str] = mapped_column(String(120), index=True)
    made_at: Mapped[datetime] = mapped_column(UTCDateTime)
    horizon_label: Mapped[str] = mapped_column(String(40))
    verdict: Mapped[str] = mapped_column(String(40))
    n_observed: Mapped[int] = mapped_column(default=0)
    n_simulated: Mapped[int] = mapped_column(default=0)
    n_missing: Mapped[int] = mapped_column(default=0)
    confidence: Mapped[float] = mapped_column(default=0.0)
    report_json: Mapped[str] = mapped_column(Text)
