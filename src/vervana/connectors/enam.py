"""eNAM connector (Part 4.4) — the highest-quality public source where coverage exists
(executed e-auction prices), but with NO documented open API. This is a deliberate stub:
the interface exists so eNAM can be slotted in the moment an access method is resolved,
but it refuses to run until then rather than pretending to have data.

Access method is unresolved — tracked in docs/OPEN_QUESTIONS.md #1.
"""

from __future__ import annotations

from vervana.connectors.base import Connector, IngestResult


class EnamAccessUnresolvedError(RuntimeError):
    """Raised because eNAM has no documented open API yet (OPEN_QUESTIONS #1)."""


class EnamConnector(Connector):
    name = "enam"

    def fetch_raw(self, **params) -> list[dict]:
        raise EnamAccessUnresolvedError(
            "eNAM has no documented open API. Only the live dashboard exists; a lawful, "
            "reliable access method is unresolved (OPEN_QUESTIONS #1). This connector is a "
            "stub until then."
        )

    def ingest(self, session, records: list[dict], *, mode: str = "enam") -> IngestResult:
        # The parse path would emit executed_trade rows (eNAM lots) — implemented once an
        # access method exists. For now nothing reaches here.
        return IngestResult(rows_in=len(records))
