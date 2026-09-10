#!/usr/bin/env python3
"""Export the manually-prepared transcript-corpus .numbers file to CSV, and print a
structural summary. One-off helper: reads a human-curated spreadsheet (NOT a scraper).
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

from numbers_parser import Document

SRC = (
    sys.argv[1]
    if len(sys.argv) > 1
    else (
        "/Users/rajeevsingh.1/Library/Mobile Documents/com~apple~Numbers/Documents/"
        "Mandi Price Data - 9 Jun to 9 Sep 2026.numbers"
    )
)
OUT = Path("data/raw/transcript/corpus.csv")


def main() -> int:
    doc = Document(SRC)
    table = doc.sheets[0].tables[0]
    rows = table.rows(values_only=True)
    header, data = rows[0], rows[1:]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(data)
    print(f"exported {len(data)} rows -> {OUT}")

    dates = [r[0] for r in data if r[0]]
    print("date span:", min(dates), "->", max(dates))
    print("\nchannels/mandis:")
    for k, v in collections.Counter(r[2] for r in data).most_common():
        print(f"  {v:5}  {k}")
    print("\ntop commodities:")
    for k, v in collections.Counter(r[3] for r in data).most_common(12):
        print(f"  {v:5}  {k}")
    both = sum(1 for r in data if r[5] is not None and r[6] is not None)
    lowonly = sum(1 for r in data if r[5] is not None and r[6] is None)
    neither = sum(1 for r in data if r[5] is None and r[6] is None)
    print(f"\nprice: both low+high={both}  low-only={lowonly}  neither={neither}")
    print("\nflag distribution:")
    for k, v in collections.Counter((r[13] or "(none)")[:50] for r in data).most_common(12):
        print(f"  {v:5}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
