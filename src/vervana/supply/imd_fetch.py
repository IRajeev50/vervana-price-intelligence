"""Fetch + parse IMD's all-India districtwise rainfall PDF (M11 rainfall feed).

IMD's Hydromet Division publishes one all-India PDF with every district's daily
and *seasonal cumulative* rainfall - actual mm, normal mm and % departure. That
cumulative departure is exactly the `rainfall_deficit_pct` supply signal, so
this module turns the manual `rainfall-import` CSV into a repeatable, sourced
fetch (`vervana supply rainfall-fetch`).

Two honest guardrails, same creed as the rest of the platform:
  * the observation date is read from the PDF's own PERIOD line - we never stamp
    today's date onto a bulletin that turns out to be stale;
  * a district row that does not parse cleanly is SKIPPED and reported, never
    guessed. Nothing here invents a number.

The row parser (`parse_rainfall_text`) is pure and works on already-extracted
text, so it is unit-tested without a real PDF; `extract_pdf_text` (pypdf) and
`fetch_pdf` (httpx) are the thin IO wrappers around it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from vervana.config import Settings, get_settings

SOURCE_NAME = "IMD Hydromet Division - all-India districtwise rainfall"

# The all-India PDF spells a few districts the older way; map watch-zone names
# (data/config/supply_zones.csv) to what appears in the bulletin. Matching is
# case-insensitive; only genuine spelling differences need an entry here.
DISTRICT_ALIASES: dict[str, tuple[str, ...]] = {
    "Solapur": ("SHOLAPUR", "SOLAPUR"),
    "Belagavi": ("BELAGAVI", "BELGAUM"),
}

# serial  DISTRICT  dailyActual dailyNormal daily%dep dailyCat  cumActual cumNormal cum%dep cumCat
_ROW = re.compile(
    r"^\s*\d+\s+"
    r"(?P<district>[A-Z][A-Z0-9 .()&/'-]+?)\s+"
    r"(?P<da>-?\d+(?:\.\d+)?)\s+(?P<dn>-?\d+(?:\.\d+)?)\s+-?\d+%\s+[A-Z]+\s+"
    r"(?P<ca>-?\d+(?:\.\d+)?)\s+(?P<cn>-?\d+(?:\.\d+)?)\s+(?P<dep>-?\d+)%\s+[A-Z]+\s*$"
)
_PERIOD = re.compile(r"PERIOD[:\s]*\d{2}-\d{2}-\d{4}\s*to\s*(\d{2})-(\d{2})-(\d{4})", re.IGNORECASE)


@dataclass(frozen=True)
class RainfallRow:
    district: str  # as printed in the PDF (upper-case)
    dep_pct: float  # cumulative % departure from normal (negative = deficit)
    actual_mm: float
    normal_mm: float


def parse_rainfall_text(text: str) -> tuple[date | None, dict[str, RainfallRow]]:
    """Parse extracted PDF text into (as-of date, {UPPER_DISTRICT: RainfallRow}).

    Pure and side-effect free. Only rows matching the full column structure are
    returned; anything else is silently left out (the caller reports coverage).
    """
    as_of: date | None = None
    m = _PERIOD.search(text)
    if m:
        dd, mm, yyyy = m.groups()
        try:
            as_of = datetime.strptime(f"{yyyy}-{mm}-{dd}", "%Y-%m-%d").date()
        except ValueError:
            as_of = None
    rows: dict[str, RainfallRow] = {}
    for line in text.splitlines():
        rm = _ROW.match(line.strip())
        if not rm:
            continue
        name = re.sub(r"\s+", " ", rm.group("district")).strip().upper()
        try:
            row = RainfallRow(
                district=name,
                dep_pct=float(rm.group("dep")),
                actual_mm=float(rm.group("ca")),
                normal_mm=float(rm.group("cn")),
            )
        except ValueError:
            continue
        # First occurrence wins; a plausibility floor keeps a mis-parse out.
        if name not in rows and -100.0 <= row.dep_pct <= 5000.0 and row.normal_mm >= 0:
            rows[name] = row
    return as_of, rows


def _lookup(zone_district: str, parsed: dict[str, RainfallRow]) -> RainfallRow | None:
    candidates = [zone_district.upper(), *DISTRICT_ALIASES.get(zone_district, ())]
    for c in candidates:
        hit = parsed.get(c.upper())
        if hit is not None:
            return hit
    return None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from the IMD PDF (pypdf; pure-Python, no poppler needed)."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fetch_pdf(url: str) -> bytes:
    """Download the all-India rainfall PDF."""
    import httpx

    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def build_records(
    zones,
    *,
    settings: Settings | None = None,
    pdf_bytes: bytes | None = None,
) -> tuple[list[dict], list[str], date | None]:
    """Fetch/parse the PDF and build rainfall-import records for the given zones.

    Returns (records, missing_districts, as_of_date). `records` are ready for
    ImdRainfallConnector.ingest; `missing_districts` are watch-zone districts the
    PDF did not yield (reported, never invented). Pass `pdf_bytes` to parse an
    already-downloaded PDF (used by tests) instead of fetching.
    """
    settings = settings or get_settings()
    url = settings.imd_all_india_rainfall_url
    if pdf_bytes is None:
        pdf_bytes = fetch_pdf(url)
    as_of, parsed = parse_rainfall_text(extract_pdf_text(pdf_bytes))
    from vervana.time import now_utc

    on_date = (as_of or now_utc().date()).isoformat()
    period = f" (cumulative to {as_of.isoformat()})" if as_of else ""
    records: list[dict] = []
    missing: list[str] = []
    seen: set[str] = set()
    for z in zones:
        if z.district in seen:
            continue
        seen.add(z.district)
        row = _lookup(z.district, parsed)
        if row is None:
            missing.append(z.district)
            continue
        records.append(
            {
                "district": z.district,
                "state": z.state,
                "date": on_date,
                "dep_pct": row.dep_pct,
                "source": SOURCE_NAME + period,
                "source_url": url,
            }
        )
    return records, missing, as_of
