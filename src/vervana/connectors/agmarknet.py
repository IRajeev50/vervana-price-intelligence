"""Agmarknet connector via data.gov.in (Part 4.1).

Agmarknet's daily resource gives each market's daily min/max/modal price per commodity —
a daily *summary* of executed trades, so rows are `executed_summary` / `daily_summary`.
Prices are ₹ per quintal (100 kg); quintal→kg is a defined conversion (seeded), so these
rows get a real canonical ₹/kg.

Robustness the spec calls for:
  * API key from env, never committed.
  * Pagination (1000-record cap), bounded retries with exponential backoff, 429 that
    pauses rather than hot-retries, 400 raised loudly (bad key/params/schema).
  * data.gov.in regularly takes >30s to answer a page, so read timeouts and other
    transport errors are RETRIED (bounded, with backoff) instead of killing the run on
    the first slow response. Timeout/retry budget is configurable via Settings
    (VERVANA_AGMARKNET_* env vars).
  * Raw payload stored before parsing.
  * Field names are NOT standardised on data.gov.in, so mapping is case-insensitive over
    candidate names and FAILS LOUDLY on a missing required field.
  * Missing/zero prices rejected with a reason; market/commodity resolved only via
    VERIFIED registry aliases — unresolved rows are rejected (recorded), never guessed.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError

from vervana.config import Settings, get_settings
from vervana.connectors.base import Connector, IngestResult
from vervana.db.base import CanonicalType, SourceClass, TimeBasis
from vervana.logging import get_logger
from vervana.models.ingest import IngestRun
from vervana.money import rupees_to_paise
from vervana.repository.prices import insert_observation
from vervana.repository.registry import resolve_by_name
from vervana.repository.units import lookup_kg_equivalent
from vervana.time import IST, now_utc

log = get_logger("vervana.connectors.agmarknet")

RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
BASE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"
PAGE_CAP = 1000  # data.gov.in per-call record cap

# Candidate field names (case-insensitive) -> canonical key. data.gov.in is not
# standardised, so we accept the documented variants and fail loudly otherwise.
FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "state": ("state",),
    "district": ("district",),
    "market": ("market",),
    "commodity": ("commodity", "commodity_name"),
    "variety": ("variety",),
    "grade": ("grade",),
    "arrival_date": ("arrival_date", "arrivaldate"),
    "min_price": ("min_price", "min price (rs./quintal)", "min_x0020_price"),
    "max_price": ("max_price", "max price (rs./quintal)", "max_x0020_price"),
    "modal_price": ("modal_price", "modal price (rs./quintal)", "modal_x0020_price"),
}
REQUIRED = ("market", "commodity", "arrival_date", "min_price", "max_price", "modal_price")
_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y")


class SchemaError(ValueError):
    """Raised when a required field is absent from a record (loud, not silent)."""


class MissingApiKeyError(RuntimeError):
    """Raised when a live fetch is attempted without VERVANA_DATA_GOV_IN_API_KEY."""


class FetchError(RuntimeError):
    """Raised when a page cannot be fetched within the bounded retry budget.

    The message is user-facing (the CLI prints it), so it names the cause, the
    configured budget, and the env vars that tune it.
    """


def _lower_keys(record: dict) -> dict:
    return {str(k).strip().lower(): v for k, v in record.items()}


def map_fields(record: dict) -> dict[str, Any]:
    """Map a raw record to canonical keys, case-insensitively. Fails loudly if incomplete."""
    low = _lower_keys(record)
    out: dict[str, Any] = {}
    for canon, candidates in FIELD_CANDIDATES.items():
        for cand in candidates:
            if cand in low:
                out[canon] = low[cand]
                break
    missing = [k for k in REQUIRED if k not in out or out[k] in (None, "")]
    if missing:
        raise SchemaError(
            f"record missing required field(s) {missing}; available keys: {sorted(low)}"
        )
    return out


def _parse_date(value: str) -> datetime:
    for fmt in _DATE_FORMATS:
        try:
            d = datetime.strptime(str(value).strip(), fmt)
            return datetime(d.year, d.month, d.day, tzinfo=IST)
        except ValueError:
            continue
    raise SchemaError(f"unparseable arrival_date {value!r}")


def _price_paise(value: Any) -> int | None:
    """Rupees-per-quintal string/number -> integer paise, or None if zero/blank."""
    s = str(value).strip()
    if s in ("", "0", "0.0", "NA", "-"):
        return None
    try:
        paise = rupees_to_paise(s)
    except Exception:
        return None
    return paise or None


class AgmarknetConnector(Connector):
    name = "agmarknet"

    def __init__(self, raw_dir: Path | None = None):
        self.raw_dir = raw_dir or (Path.cwd() / "data" / "raw" / "agmarknet")

    # --- network ---------------------------------------------------------------
    def fetch_raw(
        self,
        *,
        filters: dict[str, str] | None = None,
        max_records: int = PAGE_CAP,
        settings: Settings | None = None,
        max_retries: int | None = None,
        backoff_base: float | None = None,
        timeout_seconds: float | None = None,
        sleep=time.sleep,
    ) -> list[dict]:
        settings = settings or get_settings()
        if not settings.data_gov_in_api_key:
            raise MissingApiKeyError(
                "VERVANA_DATA_GOV_IN_API_KEY is not set; cannot fetch live Agmarknet data."
            )
        # Network budget: Settings-backed, overridable per-call (tests, scripts).
        # data.gov.in is often slow (routinely >30s/page), so the default read timeout
        # is generous and transport failures are retried rather than fatal.
        retries = settings.agmarknet_max_retries if max_retries is None else max_retries
        backoff = settings.agmarknet_backoff_base_seconds if backoff_base is None else backoff_base
        timeout = settings.agmarknet_timeout_seconds if timeout_seconds is None else timeout_seconds

        records: list[dict] = []
        offset = 0
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0)) as client:
            while len(records) < max_records:
                limit = min(PAGE_CAP, max_records - len(records))
                params = {
                    "api-key": settings.data_gov_in_api_key,
                    "format": "json",
                    "offset": offset,
                    "limit": limit,
                }
                for k, v in (filters or {}).items():
                    params[f"filters[{k}]"] = v

                page = self._get_page(client, params, retries, backoff, timeout, sleep)
                batch = page.get("records", [])
                if not batch:
                    break
                records.extend(batch)
                offset += len(batch)
                if len(batch) < limit:
                    break
        return records

    def _get_page(self, client, params, max_retries, backoff_base, timeout, sleep) -> dict:
        """Fetch one page, retrying what is retryable within a bounded budget.

        Retryable: read/connect timeouts, other transport errors, 429, 5xx, and a 200
        whose body is not JSON (data.gov.in's WAF sometimes answers an HTML error page
        with a 200). NOT retryable: 4xx like 400/401/403 — a bad key or bad params will
        fail identically on every retry, so those raise immediately.
        """
        last_error: str | None = None
        for attempt in range(max_retries):
            wait = min(backoff_base * (2**attempt), 60.0)
            try:
                resp = client.get(BASE_URL, params=params)
            except httpx.TimeoutException as exc:
                last_error = f"{type(exc).__name__} after {timeout:g}s"
                log.warning("agmarknet_timeout", attempt=attempt + 1, wait_s=wait)
                sleep(wait)
                continue
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning("agmarknet_transport_error", attempt=attempt + 1, wait_s=wait)
                sleep(wait)
                continue
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    last_error = "200 with non-JSON body (likely a WAF/proxy error page)"
                    log.warning("agmarknet_non_json_200", attempt=attempt + 1, wait_s=wait)
                    sleep(wait)
                    continue
            if resp.status_code == 429:
                # Pause rather than retry hot.
                wait = backoff_base * (2 ** (attempt + 2))
                log.warning("agmarknet_rate_limited", attempt=attempt, wait_s=wait)
                sleep(wait)
                continue
            if 500 <= resp.status_code < 600:
                log.warning(
                    "agmarknet_server_error",
                    status=resp.status_code,
                    attempt=attempt + 1,
                    wait_s=wait,
                )
                sleep(wait)
                continue
            # 400/401/403: bad key/params/schema — do not retry, fail loudly.
            resp.raise_for_status()
        raise FetchError(
            f"data.gov.in did not answer after {max_retries} attempts "
            f"(last error: {last_error or 'unknown'}). The service is often slow; "
            f"retry in a few minutes, or raise the budget via "
            f"VERVANA_AGMARKNET_TIMEOUT_SECONDS (now {timeout:g}s) and "
            f"VERVANA_AGMARKNET_MAX_RETRIES (now {max_retries}) in .env."
        )

    # --- parse/emit ------------------------------------------------------------
    def ingest(self, session, records: list[dict], *, mode: str = "daily") -> IngestResult:
        result = IngestResult(rows_in=len(records))
        for record in records:
            try:
                fields = map_fields(record)
            except SchemaError as exc:
                result.reject(f"schema_error: {exc}", record)
                continue

            commodity_id = resolve_by_name(
                session, name=str(fields["commodity"]), canonical_type=CanonicalType.commodity
            )
            if commodity_id is None:
                result.reject(f"unresolved_commodity: {fields['commodity']}", record)
                continue

            market_id = resolve_by_name(
                session, name=str(fields["market"]), canonical_type=CanonicalType.market
            )
            if market_id is None:
                result.reject(f"unresolved_market: {fields['market']}", record)
                continue

            low = _price_paise(fields["min_price"])
            high = _price_paise(fields["max_price"])
            modal = _price_paise(fields["modal_price"])
            if low is None and high is None and modal is None:
                result.reject("missing_or_zero_price", record)
                continue
            # Fill gaps sensibly without inventing precision.
            low = low or modal or high
            high = high or modal or low
            if low > high:
                result.reject("range_disorder", record)
                continue
            # Agmarknet sometimes reports a modal OUTSIDE its own [min, max] (a source data
            # error). We do not assert a point we can't trust: drop it (the range still
            # stands, canonical falls back to the midpoint). Flag, never silently correct.
            modal_out_of_range = modal is not None and not (low <= modal <= high)
            if modal_out_of_range:
                modal = None

            conv = lookup_kg_equivalent(session, unit_raw="Quintal", commodity_id=commodity_id)
            canonical = None
            kg_eq = None
            conf = None
            if conv:
                per_quintal = modal if modal is not None else round((low + high) / 2)
                canonical = round(per_quintal / conv.kg_equivalent)
                kg_eq = conv.kg_equivalent
                conf = conv.confidence

            # RISK[R4-WEAK-GROUND-TRUTH]: We record Agmarknet as `executed_summary` — a
            # trustworthy summary of the day's executed trades. But DMI disclaims its own
            # data's authenticity, and markets have been caught reporting nothing for weeks
            # (Assam, Jun-Jul 2025). So Agmarknet is NOT ground truth; it is one comparator.
            # The ground truth for validation is trader invoices (M5). Nothing downstream may
            # treat this source_class as an authoritative price.
            # Evidence: docs/RISK_REGISTER.md#r4-weak-ground-truth
            # Verdict: PENDING
            # A per-row savepoint isolates any unexpected DB constraint error to this row,
            # so one bad row can never poison the whole batch.
            try:
                with session.begin_nested():
                    insert_observation(
                        session,
                        commodity_id=commodity_id,
                        market_id=market_id,
                        source_class=SourceClass.executed_summary,
                        price_low_paise=low,
                        price_high_paise=high,
                        price_point_paise=modal,
                        unit_raw="Quintal",
                        canonical_price_paise_per_kg=canonical,
                        unit_kg_equivalent=kg_eq,
                        unit_conversion_confidence=conf,
                        source_url=BASE_URL,
                        raw_quote=json.dumps(record, ensure_ascii=False),
                        observed_at=_parse_date(fields["arrival_date"]),
                        time_basis=TimeBasis.daily_summary,
                    )
            except IntegrityError as exc:
                result.reject(f"db_constraint: {exc.orig.__class__.__name__}", record)
                continue
            result.accept()
        return result

    # --- orchestration ---------------------------------------------------------
    def ingest_with_run(self, session, records: list[dict], *, mode: str, raw_payload_path=None):
        """Ingest already-fetched records AND record an ingest_run.

        Used by the daily-capture path (records fetched out-of-process via curl), so
        every capture — even one that returns zero Delhi rows — leaves a dated run row
        that becomes the coverage history.
        """
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

    def run(self, session, *, mode: str = "daily", **fetch_params):
        """Fetch -> archive raw -> ingest -> record ingest_run. Failure leaves no partial data."""
        run = IngestRun(connector=self.name, mode=mode, status="running", started_at=now_utc())
        session.add(run)
        session.flush()
        try:
            records = self.fetch_raw(**fetch_params)
            run.raw_payload_path = self._archive(records)
            result = self.ingest(session, records, mode=mode)
            run.rows_in = result.rows_in
            run.accepted = result.accepted
            run.rejected = result.rejected
            run.rejection_reasons = result.reason_counts
            run.status = "ok"
            run.finished_at = now_utc()
            session.flush()
            return run, result
        except Exception as exc:  # fetch failure: record it, emit no partial rows
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = now_utc()
            session.flush()
            raise

    def record_failure(self, session, *, mode: str, exc: Exception) -> IngestRun:
        """Record a failed run in a FRESH transaction (CLI failure path).

        run() flushes its failed-run row into the caller's session and re-raises, so
        under `session_scope` that row is rolled back with everything else. The CLI
        catches the failure and calls this in a new session, so `vervana ingest
        history` shows the failed capture instead of a silent gap.
        """
        run = IngestRun(
            connector=self.name,
            mode=mode,
            status="failed",
            started_at=now_utc(),
            finished_at=now_utc(),
            error=f"{type(exc).__name__}: {exc}",
        )
        session.add(run)
        session.flush()
        return run

    def _archive(self, records: list[dict]) -> str:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        path = self.raw_dir / f"{now_utc().strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
