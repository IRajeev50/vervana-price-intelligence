"""Parser for IMD's all-India districtwise rainfall PDF (supply rainfall-fetch).

The row parser is pure (works on extracted text), so these tests need no real
PDF or network. Guardrails under test: the observation date comes from the PDF's
own PERIOD line, district-name aliases resolve, and a district absent from the
bulletin is reported as missing - never invented.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from vervana.supply.imd_fetch import parse_rainfall_text

# Lines exactly as pypdf extracts them from the bulletin, plus header noise.
SAMPLE = """DISTRICTWISE RAINFALL SUMMARY   DAY: 23-09-2026   PERIOD: 01-06-2026 to 23-09-2026
STATE : MAHARASHTRA
6 NASHIK 4.2 7 -40% D 1188.3 852.5 39% E
10 SHOLAPUR 8.4 6.8 23% E 184.8 412.1 -55% D
STATE : UTTAR PRADESH
1 AGRA 0 2.3 -100% NR 513.9 522.8 -2% N
a stray header line that must not parse as a district
"""


def test_parse_reads_period_date_and_rows():
    as_of, rows = parse_rainfall_text(SAMPLE)
    assert as_of == date(2026, 9, 23)
    assert set(rows) == {"NASHIK", "SHOLAPUR", "AGRA"}
    assert rows["NASHIK"].dep_pct == 39.0
    assert rows["SHOLAPUR"].dep_pct == -55.0
    assert rows["SHOLAPUR"].actual_mm == 184.8
    assert rows["SHOLAPUR"].normal_mm == 412.1
    assert rows["AGRA"].dep_pct == -2.0


def test_build_records_maps_aliases_and_reports_missing(monkeypatch):
    import vervana.supply.imd_fetch as mod

    # Parse the sample text instead of a real PDF.
    monkeypatch.setattr(mod, "extract_pdf_text", lambda _b: SAMPLE)
    zones = [
        SimpleNamespace(zone="nashik-onion", district="Nashik", state="Maharashtra"),
        SimpleNamespace(zone="solapur-sugarcane", district="Solapur", state="Maharashtra"),
        SimpleNamespace(zone="kolar-tomato", district="Kolar", state="Karnataka"),
    ]
    records, missing, as_of = mod.build_records(zones, pdf_bytes=b"pdf")
    assert as_of == date(2026, 9, 23)

    by = {r["district"]: r for r in records}
    assert by["Nashik"]["dep_pct"] == 39.0
    # "Solapur" resolves to the bulletin's "SHOLAPUR" spelling via the alias map.
    assert by["Solapur"]["dep_pct"] == -55.0
    assert by["Solapur"]["date"] == "2026-09-23"
    assert all(r["source_url"] for r in records)  # provenance never blank
    # Kolar is not in the sample -> reported, not fabricated.
    assert missing == ["Kolar"]
    assert "Kolar" not in by


def test_no_period_line_leaves_date_unknown():
    as_of, rows = parse_rainfall_text("1 AGRA 0 2.3 -100% NR 513.9 522.8 -2% N\n")
    assert as_of is None
    assert rows["AGRA"].dep_pct == -2.0
