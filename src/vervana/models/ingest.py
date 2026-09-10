"""Ingest-run metadata (Part 4): one row per connector run, for observability + audit.

Records what a run touched so a failed or partial run is never invisible: when it
started/finished, how many raw records came in, how many were accepted vs rejected,
the rejection reasons (as JSON), and where the raw payload was archived.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vervana.db.base import Base, UTCDateTime


class IngestRun(Base):
    __tablename__ = "ingest_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(20))  # 'daily' | 'backfill'
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|ok|failed

    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    rows_in: Mapped[int] = mapped_column(Integer, default=0)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)

    # {reason: count} — why rows were rejected, at a glance.
    rejection_reasons: Mapped[dict | None] = mapped_column(JSON, default=None)
    # Where the raw payload was archived before parsing (data residency: local disk).
    raw_payload_path: Mapped[str | None] = mapped_column(String(500), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
