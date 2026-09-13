"""IMD district rainfall feed (M11): the supply layer's working agromet path.

The India Meteorological Department publishes district rainfall (actual mm,
normal mm, % departure) through its rainfall pages and the daily district
rainfall distribution bulletin; the Hydromet division's CRIS portal carries the
district-level tables. Two honest paths in, no invented data:

- ``import_csv``: a CSV exported/downloaded from IMD (columns below). This is
  the path that works today.
- ``fetch_raw``: only if VERVANA_IMD_DISTRICT_RAINFALL_URL points at a
  machine-readable CSV endpoint. IMD's public bulletin is a PDF; until a stable
  CSV endpoint is configured, fetch raises and says so.

Rows become OBSERVED `rainfall_deficit_pct` signals (negative = deficit), the
production step's rain input. `source` is mandatory per row (default "IMD"):
an observed signal without a named source is a provenance lie.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from vervana.config import Settings, get_settings
from vervana.connectors.base import Connector, IngestResult
from vervana.models.context import ContextSignal

IMD_SOURCE = "IMD district rainfall"
IMD_SOURCE_URL = "https://mausam.imd.gov.in/responsive/rainfallinformation.php"


class ImdRainfallConnector(Connector):
    name = "imd-rainfall"

    def fetch_raw(self, *, settings: Settings | None = None, **params) -> list[dict]:
        """Fetch a CSV from the configured endpoint, if one is configured."""
        settings = settings or get_settings()
        if not settings.imd_district_rainfall_url:
            raise NotImplementedError(
                "no VERVANA_IMD_DISTRICT_RAINFALL_URL set - IMD's public district "
                "bulletin is a PDF, so use `vervana supply rainfall-import <csv>` "
                "with a CSV exported from IMD/CRIS. Nothing was fetched."
            )
        import httpx

        resp = httpx.get(settings.imd_district_rainfall_url, timeout=120.0)
        resp.raise_for_status()
        return list(csv.DictReader(resp.text.splitlines()))

    def import_csv(self, session: Session, path: str | Path) -> IngestResult:
        with Path(path).open(encoding="utf-8") as fh:
            return self.ingest(session, list(csv.DictReader(fh)), mode="csv")

    def ingest(self, session: Session, records: list[dict], *, mode: str = "csv") -> IngestResult:
        """Rows -> OBSERVED rainfall_deficit_pct signals.

        Accepted columns (case/space-insensitive): district, state, date,
        plus EITHER dep_pct (IMD's own % departure) OR actual_mm + normal_mm.
        """
        result = IngestResult(rows_in=len(records))
        for rec in records:
            low = {
                str(k).strip().lower().replace(" ", "_"): (v or "").strip() for k, v in rec.items()
            }
            district = low.get("district")
            on_date = self._date(low.get("date") or low.get("on_date"))
            source = low.get("source") or IMD_SOURCE
            if not district or on_date is None:
                result.reject("missing_district_or_date", rec)
                continue
            dep = self._float(low.get("dep_pct") or low.get("departure_pct"))
            if dep is None:
                actual = self._float(low.get("actual_mm"))
                normal = self._float(low.get("normal_mm"))
                if actual is None or normal is None or normal == 0:
                    result.reject("need dep_pct or actual_mm+normal_mm", rec)
                    continue
                dep = round(100.0 * (actual - normal) / normal, 2)
            session.add(
                ContextSignal(
                    signal_type="rainfall_deficit_pct",
                    region=district,
                    on_date=on_date,
                    value_numeric=dep,
                    value_text=None,
                    source=source,
                    source_url=low.get("source_url") or IMD_SOURCE_URL,
                )
            )
            result.accept()
        return result

    @staticmethod
    def _float(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value.replace("%", "").strip())
        except ValueError:
            return None

    @staticmethod
    def _date(value: str | None) -> date | None:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime((value or "").strip(), fmt).date()
            except ValueError:
                continue
        return None
