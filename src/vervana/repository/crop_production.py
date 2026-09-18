"""District crop production (DES/APY): import and honest aggregation.

The aggregation rule is the whole point of this module. DES publishes, for a
district x crop x year, EITHER:

  * one row with season="Total" (already the annual figure), OR
  * per-season rows (Kharif / Rabi / Summer / Autumn / Winter / Whole Year).

Where both exist, the Total row equals the sum of the seasonal rows. So a
district total must take the Total row when present and the seasonal sum
otherwise - Total and seasonal rows are NEVER added together. Adding them
double-counts (an earlier off-platform summary made exactly that mistake and
reported Purnia 2022-23 at ~1.59M tonnes instead of the correct ~0.82M).

Rows are stored raw (see vervana.models.crop_production); every total the
platform shows is computed here, at read time, with the rule visible.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.models.crop_production import CropProductionRecord
from vervana.time import now_utc

SOURCE_NAME = "DES district-wise season-wise crop production (Ministry of Agriculture, via India Data Portal)"
SOURCE_URL = "https://www.data.gov.in/catalog/district-wise-season-wise-crop-production-statistics-0"
SEASON_TOTAL = "Total"

_REQUIRED = ("year", "state_name", "district_name", "crop_name", "season")


def _num(value: str | None) -> float | None:
    """A blank stays None (never zero-filled); a non-number is None too."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def import_apy_csv(session: Session, path: Path) -> dict:
    """Import a DES/APY district-crop CSV. Idempotent: re-running skips existing rows."""
    existing = set(
        session.execute(
            select(
                CropProductionRecord.year_label,
                CropProductionRecord.state_name,
                CropProductionRecord.district_name,
                CropProductionRecord.crop_name,
                CropProductionRecord.season,
            )
        ).all()
    )
    added = skipped = 0
    reasons: dict[str, int] = defaultdict(int)
    stamp = now_utc()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            missing = [k for k in _REQUIRED if not (row.get(k) or "").strip()]
            if missing:
                reasons[f"missing {', '.join(missing)}"] += 1
                continue
            key = (
                row["year"].strip(),
                row["state_name"].strip(),
                row["district_name"].strip(),
                row["crop_name"].strip(),
                row["season"].strip(),
            )
            if key in existing:
                skipped += 1
                continue
            session.add(
                CropProductionRecord(
                    year_label=key[0],
                    state_name=key[1],
                    district_name=key[2],
                    crop_name=key[3],
                    season=key[4],
                    crop_type=(row.get("crop_type") or "").strip(),
                    area_ha=_num(row.get("area")),
                    production_t=_num(row.get("production")),
                    yield_t_per_ha=_num(row.get("yield")),
                    source_name=SOURCE_NAME,
                    source_url=SOURCE_URL,
                    imported_at=stamp,
                )
            )
            existing.add(key)
            added += 1
    return {"added": added, "skipped": skipped, "rejected": sum(reasons.values()), "reasons": dict(reasons)}


def _annualise(rows: list[CropProductionRecord]) -> dict:
    """One crop's rows for one district-year -> annual figures, no double-count.

    Total row when present, else the sum of the seasonal rows. `basis` records
    which leg produced the number, so the UI can show it.
    """
    total_row = next((r for r in rows if r.season == SEASON_TOTAL), None)
    seasonal = [r for r in rows if r.season != SEASON_TOTAL]
    if total_row is not None:
        return {
            "production": total_row.production_t,
            "area": total_row.area_ha,
            "yield": total_row.yield_t_per_ha,
            "basis": "annual row",
        }
    prod = [r.production_t for r in seasonal if r.production_t is not None]
    area = [r.area_ha for r in seasonal if r.area_ha is not None]
    production = sum(prod) if prod else None
    area_sum = sum(area) if area else None
    yld = round(production / area_sum, 3) if production and area_sum else None
    return {"production": production, "area": area_sum, "yield": yld, "basis": "seasonal sum"}


def district_index(session: Session) -> list[dict]:
    """Every district in store, with row counts and its latest published year."""
    rows = session.execute(
        select(
            CropProductionRecord.state_name,
            CropProductionRecord.district_name,
            func.count(),
            func.max(CropProductionRecord.year_label),
        ).group_by(CropProductionRecord.state_name, CropProductionRecord.district_name)
    ).all()
    return [
        {"state": state, "district": district, "rows": n, "latest_year": latest}
        for state, district, n, latest in sorted(rows, key=lambda r: r[1])
    ]


def fetch_year_rows(session: Session, district: str, year_label: str) -> list[CropProductionRecord]:
    return list(
        session.scalars(
            select(CropProductionRecord).where(
                CropProductionRecord.district_name == district,
                CropProductionRecord.year_label == year_label,
            )
        )
    )


def fetch_crop_rows(session: Session, district: str, crop: str) -> list[CropProductionRecord]:
    return list(
        session.scalars(
            select(CropProductionRecord).where(
                CropProductionRecord.district_name == district,
                CropProductionRecord.crop_name == crop,
            )
        )
    )


def latest_year_label(session: Session, district: str) -> str | None:
    return session.scalar(
        select(func.max(CropProductionRecord.year_label)).where(
            CropProductionRecord.district_name == district
        )
    )


def rollup_crop_year(rows: list[CropProductionRecord]) -> list[dict]:
    """All crops for one district-year, annualised, sorted by production desc."""
    by_crop: dict[str, list[CropProductionRecord]] = defaultdict(list)
    for r in rows:
        by_crop[r.crop_name].append(r)
    out = []
    for crop, crop_rows in by_crop.items():
        annual = _annualise(crop_rows)
        out.append(
            {
                "crop": crop,
                "crop_type": crop_rows[0].crop_type,
                "production": annual["production"],
                "area": annual["area"],
                "yield": annual["yield"],
                "basis": annual["basis"],
            }
        )
    out.sort(key=lambda r: (r["production"] is None, -(r["production"] or 0)))
    return out


def rollup_crop_trend(rows: list[CropProductionRecord]) -> list[dict]:
    """One crop across years, annualised per year, oldest first."""
    by_year: dict[str, list[CropProductionRecord]] = defaultdict(list)
    for r in rows:
        by_year[r.year_label].append(r)
    out = []
    for year in sorted(by_year):
        annual = _annualise(by_year[year])
        out.append(
            {
                "year": year,
                "production": annual["production"],
                "area": annual["area"],
                "yield": annual["yield"],
                "basis": annual["basis"],
            }
        )
    return out
