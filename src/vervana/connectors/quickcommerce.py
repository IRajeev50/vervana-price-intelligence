"""Quick-commerce connector (Part 4.5) — retail offers, for the HoReCa spread.

Two paths only, and deliberately NO scraper:
  * `import_csv` — the compliant path: a manual-panel CSV a human exported/typed.
  * `vendor_feed` — a documented stub that refuses to run, carrying R10 (buying feeds
    from data vendors moves the ToS breach one party away, it does not remove it).

Pack prices are normalised to ₹/kg while pack size, MRP, selling price and fees are kept
separately (retail_offer_detail). Rows are `source_class = retail_offer` and are never
averaged with wholesale (the repository guard blocks that); the value is the *spread*
shown side by side, not a blended number.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from vervana.connectors.base import Connector, IngestResult
from vervana.db.base import CanonicalType, SourceClass, TimeBasis
from vervana.models.retail import RetailOfferDetail
from vervana.money import rupees_to_paise
from vervana.repository.prices import insert_observation
from vervana.repository.registry import resolve_by_name
from vervana.time import IST

# Expected CSV columns for the manual panel.
COLUMNS = (
    "platform",
    "sku_title",
    "commodity",
    "pack_size_raw",
    "pack_kg",
    "mrp_rupees",
    "selling_price_rupees",
    "fees_rupees",
    "observed_date",
    "source_url",
)


class ScraperForbiddenError(RuntimeError):
    """Raised if anyone tries to make this connector scrape a quick-commerce app."""


class QuickCommerceConnector(Connector):
    name = "quickcommerce"

    def fetch_raw(self, **params) -> list[dict]:
        # RISK[R10-QCOMM-SOURCING]: A "vendor feed" of quick-commerce prices is not a
        # compliance escape hatch — buying scraped data from a third party moves the
        # terms-of-service breach one party away rather than removing it. This path is a
        # documented stub and must stay disabled until a genuinely licensed feed exists.
        # The ONLY supported quick-commerce path is import_csv (a human-run manual panel).
        # Evidence: docs/RISK_REGISTER.md#r10-qcomm-sourcing; Part 7 (no scraping)
        # Verdict: PENDING
        raise ScraperForbiddenError(
            "quick-commerce has no fetch path: no scraping (Part 7) and no vendor feed "
            "(R10). Use import_csv with a manual-panel export instead."
        )

    def import_csv(self, session, path: str | Path) -> IngestResult:
        rows = self._read_csv(Path(path))
        return self.ingest(session, rows, mode="csv")

    def ingest(self, session, records: list[dict], *, mode: str = "csv") -> IngestResult:
        result = IngestResult(rows_in=len(records))
        for rec in records:
            low = {str(k).strip().lower(): (v or "").strip() for k, v in rec.items()}
            commodity = low.get("commodity", "")
            commodity_id = resolve_by_name(
                session, name=commodity, canonical_type=CanonicalType.commodity
            )
            if commodity_id is None:
                result.reject(f"unresolved_commodity: {commodity}", rec)
                continue
            try:
                pack_kg = float(low.get("pack_kg") or 0)
                selling = rupees_to_paise(low["selling_price_rupees"])
                mrp = rupees_to_paise(low["mrp_rupees"]) if low.get("mrp_rupees") else None
                fees = rupees_to_paise(low["fees_rupees"]) if low.get("fees_rupees") else None
            except Exception as exc:
                result.reject(f"parse_error: {exc}", rec)
                continue
            if pack_kg <= 0 or selling <= 0:
                result.reject("missing_pack_kg_or_price", rec)
                continue
            source_url = low.get("source_url") or ""
            if not source_url:
                result.reject("missing_source_url", rec)  # provenance is required
                continue

            canonical = round(selling / pack_kg)  # ₹/kg in paise
            obs = insert_observation(
                session,
                commodity_id=commodity_id,
                market_id=self._retail_market_id(session),
                source_class=SourceClass.retail_offer,
                price_low_paise=selling,
                price_high_paise=selling,
                price_point_paise=selling,
                unit_raw=low.get("pack_size_raw") or f"{pack_kg} kg",
                canonical_price_paise_per_kg=canonical,
                unit_kg_equivalent=pack_kg,
                unit_conversion_confidence=1.0,
                source_url=source_url,
                raw_quote=json.dumps(rec, ensure_ascii=False),
                observed_at=self._parse_date(low.get("observed_date")),
                time_basis=TimeBasis.exact,
            )
            session.add(
                RetailOfferDetail(
                    observation_id=obs.id,
                    platform=low.get("platform") or "unknown",
                    sku_title=low.get("sku_title") or "",
                    pack_size_raw=low.get("pack_size_raw") or f"{pack_kg} kg",
                    pack_kg=pack_kg,
                    mrp_paise=mrp,
                    selling_price_paise=selling,
                    fees_paise=fees,
                )
            )
            session.flush()
            result.accept()
        return result

    def _retail_market_id(self, session) -> int:
        """A synthetic 'market' for online retail, created once (retail has no mandi)."""
        from sqlalchemy import select

        from vervana.models.entities import Market

        m = session.scalar(select(Market).where(Market.canonical_name == "Quick-commerce (online)"))
        if m is None:
            m = Market(canonical_name="Quick-commerce (online)", city="Delhi", state="Delhi")
            session.add(m)
            session.flush()
        return m.id

    @staticmethod
    def _parse_date(value: str | None):
        from datetime import datetime

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                d = datetime.strptime((value or "").strip(), fmt)
                return datetime(d.year, d.month, d.day, tzinfo=IST)
            except ValueError:
                continue
        from vervana.time import now_utc

        return now_utc()

    @staticmethod
    def _read_csv(path: Path) -> list[dict]:
        with path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
