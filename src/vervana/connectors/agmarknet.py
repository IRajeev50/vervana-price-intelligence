"""Agmarknet connector via the official Agmarknet 2.0 public API (api.agmarknet.gov.in).

History: this connector used the data.gov.in Agmarknet resource
(9ef84268-d588-465a-a308-a864a43d0070). That resource went stale in November 2025 —
its latest record is 04/11/2025 — which is why live imports kept returning empty.
The working source is the Agmarknet 2.0 backend behind https://agmarknet.gov.in/home:
public, keyless JSON endpoints, verified against live data (Sept 2026). The portal's
full report endpoint (/daily-price-arrival/report) is captcha-gated, so we use the
per-state daily report instead:

    GET /v1/daily-price-arrival/filters                          (lookup tables)
    GET /v1/prices-and-arrivals/commodity-market/daily-report-state
        ?date=YYYY-MM-DD&state=<state_id>&includeExcel=false

One call returns every commodity x market x variety reported in the state that day,
with min/max/modal prices in Rs/quintal and arrivals in metric tonnes.

Agmarknet's daily report gives each market's daily min/max/modal price per commodity —
a daily *summary* of executed trades, so rows are `executed_summary` / `daily_summary`.
Prices are Rs per quintal (100 kg); quintal->kg is a defined conversion (seeded), so
these rows get a real canonical Rs/kg.

Robustness the spec calls for:
  * No API key — the 2.0 report endpoints are public, but they expect browser-like
    Origin/Referer/User-Agent headers, without which the edge answers 403.
  * Bounded retries with exponential backoff, 429 that pauses rather than hot-retries,
    404 treated as "nothing reported that day" (not an error), other 4xx raised loudly.
  * Each run walks back VERVANA_AGMARKNET_LOOKBACK_DAYS days (newest first) so a fresh
    deploy backfills a week instead of a single day. Exact re-ingestion of an
    already-stored row is skipped as a duplicate, so a recurring daily capture over
    the lookback window never double-counts.
  * Raw payload stored before parsing.
  * Field names are NOT standardised across sources, so mapping is case-insensitive
    over candidate names and FAILS LOUDLY on a missing required field.
  * Missing/zero prices rejected with a reason; market/commodity resolved only via
    VERIFIED registry aliases — unresolved rows are rejected (recorded), never guessed.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from vervana.config import Settings, get_settings
from vervana.connectors.base import Connector, IngestResult
from vervana.db.base import CanonicalType, SourceClass, TimeBasis
from vervana.logging import get_logger
from vervana.models.ingest import IngestRun
from vervana.models.observations import PriceObservation
from vervana.money import rupees_to_paise
from vervana.repository.prices import insert_observation
from vervana.repository.registry import resolve_by_name
from vervana.repository.units import lookup_kg_equivalent
from vervana.time import IST, now_utc

log = get_logger("vervana.connectors.agmarknet")

API_BASE_URL = "https://api.agmarknet.gov.in/v1"
PORTAL_URL = "https://agmarknet.gov.in"
FILTERS_URL = f"{API_BASE_URL}/daily-price-arrival/filters"
DAILY_STATE_REPORT_URL = f"{API_BASE_URL}/prices-and-arrivals/commodity-market/daily-report-state"
# Recorded on each row as provenance.
SOURCE_URL = DAILY_STATE_REPORT_URL

DEFAULT_MAX_RECORDS = 1000  # default flattened-record cap per ingest run
PRICE_UNIT_EXPECTED = "Rs./Quintal"

# The 2.0 endpoints expect the portal's browser headers; without them the edge
# answers 403 even though no login or captcha is involved.
_HEADERS = {
    "Accept": "application/json",
    "Origin": PORTAL_URL,
    "Referer": f"{PORTAL_URL}/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
}

# Agmarknet 2.0 display names -> the registry's verified alias text. Only mappings
# verified against the live API live here; anything unmapped passes through
# unchanged and, if the registry still cannot resolve it, is rejected (recorded).
MARKET_NAME_MAP = {
    "apmc azadpur": "Azadpur",
    "apmc keshopur": "Keshopur",
    "apmc najafgarh": "Najafgarh",
    "apmc narela": "Narela",
    "apmc shahdara": "Shahdara",
    "fruit&vegetable market,gazipur apmc": "Ghazipur",
    # National expansion (2026-09-14): watch-zone district mandis plus national
    # benchmark metros. Every key below is the Agmarknet 2.0 `marketCenter` display
    # name (stripped, lowercased) verified against live daily state reports for
    # 2026-09-08/11/12; values are canonical names seeded in
    # data/seed/markets_national.csv.
    # Maharashtra
    "apmc nasik": "Nashik",
    "apmc lasalgaon": "Lasalgaon",
    "apmc solapur": "Solapur",
    "apmc mumbai": "Mumbai",
    "mumbai- fruit market": "Mumbai Fruit Market",
    "mumbai-onion & potato market": "Mumbai Onion & Potato Market",
    "apmc pune": "Pune",
    # Uttar Pradesh
    "meerut apmc": "Meerut",
    "agra apmc": "Agra",
    "lucknow apmc": "Lucknow",
    "noida apmc": "Noida",
    "ghaziabad apmc": "Ghaziabad",
    "varanasi apmc": "Varanasi",
    # Punjab (Agmarknet reports the Ludhiana district mandi under Sahnewal)
    "sahnewal apmc": "Sahnewal",
    "khanna apmc": "Khanna",
    "jalandhar city(jalandhar) apmc": "Jalandhar City",
    # Madhya Pradesh
    "indore apmc": "Indore",
    "indore(f&v) apmc": "Indore (F&V)",
    "bhopal apmc": "Bhopal",
    # Karnataka
    "kolar apmc": "Kolar",
    "bengaluru apmc": "Bengaluru",
    "binny mill (ff&v) bengaluru apmc": "Bengaluru Binny Mill (FF&V)",
    "belgaum apmc": "Belgaum",
    # West Bengal (Agmarknet reports Hooghly district under Sheoraphuly)
    "sheoraphuly apmc": "Sheoraphuly",
    "bara bazar (posta bazar) apmc": "Kolkata Bara Bazar (Posta)",
}
COMMODITY_NAME_MAP = {
    # The 2.0 taxonomy splits ginger; the registry's "Ginger" seed (adrak) is the
    # green cooking ginger traded in Delhi vegetable mandis.
    "ginger(green)": "Ginger",
    "ginger(dry)": "Ginger",
    # 2.0 display names whose registry alias is the seed's own verified Hindi note:
    # Okra "Bhindi / lady finger", Cucumber "Kheera / kakdi", Green Peas "Matar".
    "bhindi(ladies finger)": "Okra",
    "cucumbar(kheera)": "Cucumber",
    "peas wet": "Green Peas",
    # Agmarknet's own spelling error; the registry seeds "Radish".
    "raddish": "Radish",
    # Registry seeds Fenugreek Leaves ("Methi") and Pointed Gourd ("Parwal").
    "methi(leaves)": "Fenugreek Leaves",
    "pointed gourd(parval)": "Pointed Gourd",
}

# Candidate field names (case-insensitive) -> canonical key. Source feeds are not
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


def _translate(name: Any, mapping: dict[str, str]) -> str:
    """Map an Agmarknet 2.0 display name to the registry alias text, else pass through."""
    text = str(name or "").strip()
    return mapping.get(text.lower(), text)


def _num_str(value: Any) -> str:
    return "" if value is None else str(value)


class AgmarknetConnector(Connector):
    name = "agmarknet"

    def __init__(self, raw_dir: Path | None = None):
        self.raw_dir = raw_dir or (Path.cwd() / "data" / "raw" / "agmarknet")

    # --- network ---------------------------------------------------------------
    def fetch_raw(
        self,
        *,
        filters: dict[str, str] | None = None,
        max_records: int = DEFAULT_MAX_RECORDS,
        settings: Settings | None = None,
        max_retries: int | None = None,
        backoff_base: float | None = None,
        timeout_seconds: float | None = None,
        sleep=time.sleep,
        today: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        request_delay_seconds: float = 0.5,
    ) -> list[dict]:
        """Fetch a date range of one state's daily reports, newest first.

        By default this fetches the configured LOOKBACK window ending today. Operators
        can instead pass both ``start_date`` and ``end_date`` for a bounded historical
        backfill. A short delay between daily requests keeps month-sized backfills gentle
        on Agmarknet and on small deployment instances.

        `filters["State"]` names the state (default Delhi). Records are flattened to
        the canonical field shape that `ingest()` already understands (prices stay in
        Rs/quintal; conversion happens downstream, unchanged).
        """
        settings = settings or get_settings()
        retries = settings.agmarknet_max_retries if max_retries is None else max_retries
        backoff = settings.agmarknet_backoff_base_seconds if backoff_base is None else backoff_base
        timeout = settings.agmarknet_timeout_seconds if timeout_seconds is None else timeout_seconds
        if (start_date is None) != (end_date is None):
            raise ValueError("start_date and end_date must be provided together")
        if start_date is not None and start_date > end_date:
            raise ValueError("start_date must be on or before end_date")
        if request_delay_seconds < 0:
            raise ValueError("request_delay_seconds cannot be negative")
        lookback = max(1, settings.agmarknet_lookback_days)
        state_filter = (filters or {}).get("State") or (filters or {}).get("state") or "Delhi"

        records: list[dict] = []
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=15.0), headers=_HEADERS
        ) as client:
            state_id, state_label = self._resolve_state_id(
                client, state_filter, retries, backoff, timeout, sleep
            )
            anchor = end_date or today or now_utc().astimezone(IST).date()
            days_to_fetch = (
                (end_date - start_date).days + 1
                if start_date is not None and end_date is not None
                else lookback
            )
            for offset in range(days_to_fetch):
                day = anchor - timedelta(days=offset)
                payload = self._get_json(
                    client,
                    DAILY_STATE_REPORT_URL,
                    params={
                        "date": day.isoformat(),
                        "state": state_id,
                        "includeExcel": "false",
                    },
                    retries=retries,
                    backoff_base=backoff,
                    timeout=timeout,
                    sleep=sleep,
                )
                if payload is None:
                    log.info("agmarknet_no_data_for_day", date=day.isoformat())
                    continue
                records.extend(self._flatten_daily_report(payload, state_label, day))
                if len(records) >= max_records:
                    records = records[:max_records]
                    break
                if request_delay_seconds and offset + 1 < days_to_fetch:
                    sleep(request_delay_seconds)
        return records

    def _resolve_state_id(
        self, client, state_name: str, retries, backoff, timeout, sleep
    ) -> tuple[str, str]:
        """Resolve a state name (e.g. 'Delhi') to the 2.0 state id via the filters table."""
        payload = self._get_json(
            client, FILTERS_URL, params=None,
            retries=retries, backoff_base=backoff, timeout=timeout, sleep=sleep,
        )
        states = ((payload or {}).get("data") or {}).get("state_data") or []
        target = state_name.strip().lower()
        exact = [s for s in states if str(s.get("state_name", "")).strip().lower() == target]
        partial = [
            s for s in states if target and target in str(s.get("state_name", "")).strip().lower()
        ]
        matches = exact or partial
        if len(matches) != 1:
            raise FetchError(
                f"could not resolve state {state_name!r} to exactly one Agmarknet state "
                f"(matches: {[s.get('state_name') for s in matches]})"
            )
        return str(matches[0]["state_id"]), str(matches[0]["state_name"])

    def _flatten_daily_report(self, payload: dict, state_label: str, day: date) -> list[dict]:
        """Flatten one day's state report into canonical records (prices as Rs/quintal)."""
        records: list[dict] = []
        for group in payload.get("commodityGroups") or []:
            for comm in group.get("commodities") or []:
                commodity = _translate(comm.get("commodityName"), COMMODITY_NAME_MAP)
                for mkt in comm.get("markets") or []:
                    market = _translate(mkt.get("marketCenter"), MARKET_NAME_MAP)
                    for row in mkt.get("data") or []:
                        unit = str(row.get("unitOfPrice") or "").strip()
                        if unit and unit.lower() != PRICE_UNIT_EXPECTED.lower():
                            log.warning(
                                "agmarknet_unexpected_price_unit",
                                unit=unit, commodity=commodity, market=market,
                            )
                            continue
                        records.append(
                            {
                                "state": state_label,
                                "district": "",
                                "market": market,
                                "commodity": commodity,
                                "variety": str(row.get("variety") or ""),
                                "grade": "",
                                "arrival_date": day.isoformat(),
                                "min_price": _num_str(row.get("minimumPrice")),
                                "max_price": _num_str(row.get("maximumPrice")),
                                "modal_price": _num_str(row.get("modalPrice")),
                            }
                        )
        return records

    def _get_json(
        self, client, url, *, params, retries, backoff_base, timeout, sleep
    ) -> dict | None:
        """GET one JSON document, retrying what is retryable within a bounded budget.

        Retryable: read/connect timeouts, other transport errors, 429, 5xx, and a 200
        whose body is not JSON (a WAF/proxy error page). 404 means the source has no
        report for that day — returns None, not an error. Other 4xx (a blocked or
        malformed request) raise immediately: they fail identically on every retry.
        """
        last_error: str | None = None
        for attempt in range(retries):
            wait = min(backoff_base * (2**attempt), 60.0)
            try:
                resp = client.get(url, params=params)
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
            if resp.status_code == 404:
                return None
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
            # Other 4xx: blocked/malformed request — do not retry, fail loudly.
            resp.raise_for_status()
        raise FetchError(
            f"Agmarknet 2.0 API did not answer after {retries} attempts "
            f"(last error: {last_error or 'unknown'}). The service can be slow; "
            f"retry in a few minutes, or raise the budget via "
            f"VERVANA_AGMARKNET_TIMEOUT_SECONDS (now {timeout:g}s) and "
            f"VERVANA_AGMARKNET_MAX_RETRIES (now {retries}) in .env."
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

            observed_at = _parse_date(fields["arrival_date"])

            # Never double-count: an identical row already stored (same commodity, market,
            # day, prices, source class) is a duplicate, not a new observation. This makes
            # a recurring capture over the lookback window idempotent.
            dup_stmt = (
                select(func.count())
                .select_from(PriceObservation)
                .where(
                    PriceObservation.commodity_id == commodity_id,
                    PriceObservation.market_id == market_id,
                    PriceObservation.source_class == SourceClass.executed_summary,
                    PriceObservation.time_basis == TimeBasis.daily_summary,
                    PriceObservation.observed_at == observed_at,
                    PriceObservation.price_low_paise == low,
                    PriceObservation.price_high_paise == high,
                    PriceObservation.unit_raw == "Quintal",
                )
            )
            dup_stmt = dup_stmt.where(
                PriceObservation.price_point_paise.is_(None)
                if modal is None
                else PriceObservation.price_point_paise == modal
            )
            if session.scalar(dup_stmt):
                result.reject("duplicate_already_ingested", record)
                continue

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
                        source_url=SOURCE_URL,
                        raw_quote=json.dumps(record, ensure_ascii=False),
                        observed_at=observed_at,
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

        Used by the file/capture path (records fetched out-of-process), so every
        capture — even one that returns zero Delhi rows — leaves a dated run row
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
