"""Field-observer ingest (Part 4.3).

Observers submit price quotes from the mandi floor. The full path is voice note → ASR →
the same parser; ASR is an external/metered service, so it is a documented stub here and
the shipped path is a structured CSV a human fills (or an ASR transcript once wired).

Every observation carries the observer's independence status (R11): a report from an
observer who trades in the commodity is stored, but flagged, never treated as neutral.
Observer quotes are `source_class = quote_indicative`.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy import select

from vervana.connectors.base import Connector, IngestResult
from vervana.db.base import CanonicalType, SourceClass, TimeBasis
from vervana.models.observer import Observer
from vervana.money import rupees_to_paise
from vervana.repository.prices import insert_observation
from vervana.repository.registry import resolve_by_name
from vervana.time import now_utc


class AsrNotConfiguredError(RuntimeError):
    """ASR (voice-note → text) is an external/metered service, not wired in this build."""


def transcribe(audio_path: str) -> str:  # pragma: no cover - external service
    raise AsrNotConfiguredError(
        "ASR is not configured. Provide a transcript/CSV, or wire a metered ASR provider "
        "(cost + residency decision) — then feed its text through the same parser."
    )


class ObserverConnector(Connector):
    name = "observer"

    def fetch_raw(self, **params) -> list[dict]:
        raise NotImplementedError("observer data is pushed (CSV/transcript), not fetched")

    def import_csv(self, session, path: str | Path) -> IngestResult:
        with Path(path).open(encoding="utf-8") as fh:
            return self.ingest(session, list(csv.DictReader(fh)), mode="csv")

    def ingest(self, session, records: list[dict], *, mode: str = "csv") -> IngestResult:
        result = IngestResult(rows_in=len(records))
        for rec in records:
            low = {str(k).strip().lower(): (v or "").strip() for k, v in rec.items()}
            observer = self._observer(session, low)
            if observer is None:
                result.reject("unknown_observer", rec)
                continue
            commodity_id = resolve_by_name(
                session, name=low.get("commodity", ""), canonical_type=CanonicalType.commodity
            )
            if commodity_id is None:
                result.reject(f"unresolved_commodity: {low.get('commodity')}", rec)
                continue
            market_id = resolve_by_name(
                session, name=low.get("market", ""), canonical_type=CanonicalType.market
            )
            if market_id is None:
                result.reject(f"unresolved_market: {low.get('market')}", rec)
                continue
            try:
                lo = rupees_to_paise(low["price_low_rupees"])
                hi = rupees_to_paise(low.get("price_high_rupees") or low["price_low_rupees"])
            except Exception as exc:
                result.reject(f"parse_error: {exc}", rec)
                continue
            if lo > hi:
                result.reject("range_disorder", rec)
                continue

            insert_observation(
                session,
                commodity_id=commodity_id,
                market_id=market_id,
                source_class=SourceClass.quote_indicative,
                price_low_paise=lo,
                price_high_paise=hi,
                unit_raw=low.get("unit_raw") or "kg",
                # Observer quotes are usually per-kg already; canonical only when unit is kg.
                canonical_price_paise_per_kg=round((lo + hi) / 2)
                if (low.get("unit_raw") or "kg").lower() in ("kg", "kilo", "kilogram")
                else None,
                unit_conversion_confidence=1.0
                if (low.get("unit_raw") or "kg").lower() in ("kg", "kilo", "kilogram")
                else None,
                source_url=low.get("source_url") or f"observer:{observer.id}",
                raw_quote=json.dumps(rec, ensure_ascii=False),
                observed_at=now_utc(),
                time_basis=TimeBasis.single_daily_quote,
                observer_id=observer.id,
            )
            result.accept()
        return result

    @staticmethod
    def _observer(session, low: dict) -> Observer | None:
        if low.get("observer_id"):
            return session.get(Observer, int(low["observer_id"]))
        if low.get("observer_name"):
            return session.scalar(select(Observer).where(Observer.name == low["observer_name"]))
        return None


def add_observer(
    session, *, name: str, role: str, trades_in_reported: bool, notes: str = ""
) -> Observer:
    obs = Observer(
        name=name, role=role, trades_in_reported_commodities=trades_in_reported, notes=notes or None
    )
    session.add(obs)
    session.flush()
    return obs
