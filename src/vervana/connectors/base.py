"""Connector interface (Part 4).

Every data source is an independent connector behind this interface, and can be
disabled via config without breaking anything else. The shape is deliberately small:

    fetch_raw(...)  -> list[dict]        # network (or a fixture in tests)
    ingest(session, records, run) -> IngestResult   # normalise -> validate -> emit rows

`run()` ties them together and records an `ingest_run`. Tests call `ingest()` directly
with fixture records so nothing touches the network (Part 1.5).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from vervana.config import Settings, get_settings


@dataclass
class IngestResult:
    rows_in: int = 0
    accepted: int = 0
    rejected: int = 0
    rejections: list[tuple[str, dict]] = field(default_factory=list)  # (reason, raw record)

    def reject(self, reason: str, record: dict) -> None:
        self.rejected += 1
        self.rejections.append((reason, record))

    def accept(self) -> None:
        self.accepted += 1

    @property
    def reason_counts(self) -> dict[str, int]:
        return dict(Counter(reason for reason, _ in self.rejections))


class Connector(ABC):
    """Base class for all source connectors."""

    #: stable short name, used in config and ingest_run rows
    name: str = "base"

    def enabled(self, settings: Settings | None = None) -> bool:
        """A connector is enabled unless listed in VERVANA_DISABLED_CONNECTORS."""
        settings = settings or get_settings()
        disabled = {c.strip() for c in (settings.disabled_connectors or "").split(",") if c.strip()}
        return self.name not in disabled

    @abstractmethod
    def fetch_raw(self, **params) -> list[dict]:
        """Fetch raw records from the source (network). Not called in offline tests."""

    @abstractmethod
    def ingest(self, session: Session, records: list[dict], *, mode: str) -> IngestResult:
        """Normalise, validate, and emit rows from already-fetched raw records."""

    def ingest_with_run(
        self, session: Session, records: list[dict], *, mode: str, raw_payload_path=None
    ):
        """Ingest already-fetched records AND record an ingest_run (audit trail)."""
        from vervana.models.ingest import IngestRun
        from vervana.time import now_utc

        run = IngestRun(
            connector=self.name,
            mode=mode,
            status="running",
            started_at=now_utc(),
            raw_payload_path=str(raw_payload_path) if raw_payload_path else None,
        )
        session.add(run)
        session.flush()
        result = self.ingest(session, records, mode=mode)
        run.rows_in = result.rows_in
        run.accepted = result.accepted
        run.rejected = result.rejected
        run.rejection_reasons = result.reason_counts
        run.status = "ok"
        run.finished_at = now_utc()
        session.flush()
        return run, result
