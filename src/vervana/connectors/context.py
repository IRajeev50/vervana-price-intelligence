"""Context-signal ingest (Part 4.6): weather / diesel / festival, as model features.

These are NOT price observations — they go to `context_signal`, a separate table, so a
weather value can never be mistaken for a price. CSV import path (a human or a metered
weather/fuel API export).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from vervana.connectors.base import Connector, IngestResult
from vervana.models.context import ContextSignal


class ContextConnector(Connector):
    name = "context"

    def fetch_raw(self, **params) -> list[dict]:
        raise NotImplementedError("context signals are imported from CSV/API exports")

    def import_csv(self, session, path: str | Path) -> IngestResult:
        with Path(path).open(encoding="utf-8") as fh:
            return self.ingest(session, list(csv.DictReader(fh)), mode="csv")

    def ingest(self, session, records: list[dict], *, mode: str = "csv") -> IngestResult:
        result = IngestResult(rows_in=len(records))
        for rec in records:
            low = {str(k).strip().lower(): (v or "").strip() for k, v in rec.items()}
            try:
                on_date = self._date(low.get("date") or low.get("on_date"))
                value = float(low["value_numeric"]) if low.get("value_numeric") else None
            except Exception as exc:
                result.reject(f"parse_error: {exc}", rec)
                continue
            if not low.get("signal_type") or on_date is None:
                result.reject("missing_type_or_date", rec)
                continue
            session.add(
                ContextSignal(
                    signal_type=low["signal_type"],
                    region=low.get("region") or "Delhi",
                    on_date=on_date,
                    value_numeric=value,
                    value_text=low.get("value_text") or None,
                    source=low.get("source") or "manual",
                    source_url=low.get("source_url") or None,
                )
            )
            result.accept()
        return result

    @staticmethod
    def _date(value):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime((value or "").strip(), fmt).date()
            except ValueError:
                continue
        return None
