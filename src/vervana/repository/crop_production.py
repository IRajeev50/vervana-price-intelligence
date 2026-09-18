"""District crop production (DES/APY): import, rollup, and honest aggregation.

The aggregation rule is the whole point of this module. DES publishes, for a
district x crop x year, EITHER:

  * one row with season="Total" (already the annual figure), OR
  * per-season rows (Kharif / Rabi / Summer / Autumn / Winter / Whole Year).

Where both exist, the Total row equals the sum of the seasonal rows. So a
district total must take the Total row when present and the seasonal sum
otherwise - Total and seasonal rows are NEVER added together. Adding them
double-counts (an earlier off-platform summary made exactly that mistake and
reported Purnia 2022-23 at ~1.59M tonnes instead of the correct ~0.82M).

Rows are stored raw (see vervana.models.crop_production). Because the national
file holds ~455k raw rows across 740 districts, read-time aggregation for
directory pages runs against a derived rollup table
(crop_district_year_rollup), rebuilt from the raw rows by rebuild_rollup().
The rollup applies exactly the rule above, in SQL, and records which leg
("annual row" / "seasonal sum") produced every figure.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from sqlalchemy import and_, case, delete, func, insert, select
from sqlalchemy.orm import Session

from vervana.models.crop_production import CropDistrictYearRollup, CropProductionRecord
from vervana.time import now_utc

SOURCE_NAME = "DES district-wise season-wise crop production (Ministry of Agriculture, via India Data Portal)"
SOURCE_URL = "https://www.data.gov.in/catalog/district-wise-season-wise-crop-production-statistics-0"
# Full all-India file (34 states/UTs, 740 districts, 1997-98 to 2022-23, ~455k
# rows). Keyless download from the India Data Portal (the portal's copy of the
# same DES/APY publication); verified reachable 2026-09-18. NITI for States
# aggregates this same source and offers no usable public API.
NATIONAL_APY_URL = (
    "https://ckandev.indiadataportal.com/dataset/f2bbc28c-6c7c-462b-9064-ea4c4213d466"
    "/resource/f980409d-49a2-42ae-9eb0-182365005c04/download/crop-wise-area-production-yield.csv"
)
SEASON_TOTAL = "Total"
BASIS_ANNUAL = "annual row"
BASIS_SEASONAL = "seasonal sum"

_REQUIRED = ("year", "state_name", "district_name", "crop_name", "season")
_IMPORT_BATCH = 2000


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
    """Import a DES/APY district-crop CSV. Idempotent: re-running skips existing rows.

    Flushes and commits in batches so the full national file (~455k rows) does
    not accumulate as pending ORM objects in one transaction.
    """
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
    pending = 0
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
            pending += 1
            if pending >= _IMPORT_BATCH:
                session.flush()
                session.commit()
                pending = 0
    session.flush()
    session.commit()
    return {"added": added, "skipped": skipped, "rejected": sum(reasons.values()), "reasons": dict(reasons)}


# ---------------------------------------------------------------------------
# Rollup rebuild (raw rows -> derived read model), the rule applied in SQL.
# ---------------------------------------------------------------------------


def rebuild_rollup(session: Session) -> int:
    """Rebuild crop_district_year_rollup from the raw rows. Returns row count.

    For each state x district x year x crop: the official annual row's figures
    when one exists (basis "annual row", even when its figures are blank -
    exactly what _annualise does), otherwise the seasonal sums (basis
    "seasonal sum"). Total and seasonal rows are never added together.
    """
    R = CropProductionRecord
    is_total = R.season == SEASON_TOTAL
    grouped = (
        select(
            R.state_name.label("state_name"),
            R.district_name.label("district_name"),
            R.year_label.label("year_label"),
            R.crop_name.label("crop_name"),
            func.max(R.crop_type).label("crop_type"),
            func.max(case((is_total, 1), else_=0)).label("has_total"),
            func.max(case((is_total, R.production_t), else_=None)).label("total_prod"),
            func.max(case((is_total, R.area_ha), else_=None)).label("total_area"),
            func.max(case((is_total, R.yield_t_per_ha), else_=None)).label("total_yield"),
            func.sum(case((R.season != SEASON_TOTAL, R.production_t), else_=None)).label("season_prod"),
            func.sum(case((R.season != SEASON_TOTAL, R.area_ha), else_=None)).label("season_area"),
        )
        .group_by(R.state_name, R.district_name, R.year_label, R.crop_name)
        .subquery()
    )
    g = grouped.c
    has_total = g.has_total == 1
    production = case((has_total, g.total_prod), else_=g.season_prod)
    area = case((has_total, g.total_area), else_=g.season_area)
    seasonal_yield = case(
        (
            and_(g.season_prod.is_not(None), g.season_area.is_not(None), g.season_area > 0),
            func.round(g.season_prod / g.season_area, 3),
        ),
        else_=None,
    )
    yield_col = case((has_total, g.total_yield), else_=seasonal_yield)
    basis = case((has_total, BASIS_ANNUAL), else_=BASIS_SEASONAL)

    session.execute(delete(CropDistrictYearRollup))
    result = session.execute(
        insert(CropDistrictYearRollup).from_select(
            [
                "state_name",
                "district_name",
                "year_label",
                "crop_name",
                "crop_type",
                "production_t",
                "area_ha",
                "yield_t_per_ha",
                "basis",
            ],
            select(
                g.state_name,
                g.district_name,
                g.year_label,
                g.crop_name,
                g.crop_type,
                production,
                area,
                yield_col,
                basis,
            ),
        )
    )
    session.commit()
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# Directory + detail reads (rollup-backed, national scale).
# ---------------------------------------------------------------------------

# Fruits and vegetables are the perishable supply: the crop types whose
# production points at cold-chain and verification demand. Type labels are the
# source's own ("Vegetable" singular, as DES publishes it).
PERISHABLE_CROP_TYPES = frozenset({"Fruits", "Vegetable"})

# The national file stamps every row "Tonnes", but DES publishes coconut in
# NUTS - and the file carries the nuts figure with the "Tonnes" label anyway
# (Tumakuru 2022-23: 1.58 billion "tonnes" of coconut, i.e. nuts). Nuts are
# not tonnes: coconut is never added to tonne totals or top-crop rankings, and
# is labelled "nuts" wherever it appears. Raw rows stay exactly as published.
NON_TONNE_CROPS = {"Coconut": "nuts"}

SORTS = ("production", "perishable", "vs5", "name")


def district_directory(session: Session, state: str = "", q: str = "", sort: str = "production") -> dict:
    """Every district in store with just its key figures, for the list view.

    Per district: its latest published year's total production, top crops,
    perishable share, and the change versus the average of the five preceding
    years. Keyed by (state, district) - district names repeat across states
    (e.g. Aurangabad exists in Bihar and Maharashtra).

    Two grouped passes over the rollup: district-year totals (all years, for
    the latest-year and vs-5yr figures) and per-crop rows at each district's
    own latest year (for top crops and perishable share). Districts whose data
    stops before the national latest year still appear, at their own latest.
    """
    T = CropDistrictYearRollup
    total_rows = session.execute(
        select(
            T.state_name,
            T.district_name,
            T.year_label,
            func.sum(case((T.crop_name.not_in(NON_TONNE_CROPS), T.production_t), else_=None)),
        ).group_by(T.state_name, T.district_name, T.year_label)
    ).all()
    if not total_rows:
        return {"states": [], "rows": [], "latest_year": None}

    totals: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    tonne_totals: dict[tuple[str, str, str], float] = {}
    for st, dist, year, prod in total_rows:
        totals[(st, dist)][year] = float(prod or 0)
        tonne_totals[(st, dist, year)] = float(prod or 0)

    latest_per_district = (
        select(T.state_name, T.district_name, func.max(T.year_label).label("latest"))
        .group_by(T.state_name, T.district_name)
        .subquery()
    )
    m = latest_per_district.c
    crop_rows = session.execute(
        select(T.state_name, T.district_name, T.crop_name, T.crop_type, T.production_t).join(
            latest_per_district,
            and_(
                T.state_name == m.state_name,
                T.district_name == m.district_name,
                T.year_label == m.latest,
            ),
        )
    ).all()
    crops_at_latest: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for st, dist, crop, ctype, prod in crop_rows:
        if crop not in NON_TONNE_CROPS:
            crops_at_latest[(st, dist)].append((crop, ctype, float(prod) if prod is not None else None))

    out = []
    for (st, dist), years in totals.items():
        dlatest = max(years)
        total = tonne_totals.get((st, dist, dlatest), 0.0)
        crops = crops_at_latest.get((st, dist), [])
        perishable = sum(
            p for _, ctype, p in crops if p is not None and ctype in PERISHABLE_CROP_TYPES
        )
        prev5 = [tonne_totals.get((st, dist, y), 0.0) for y in sorted(y for y in years if y < dlatest)[-5:]]
        prev5_avg = sum(prev5) / len(prev5) if prev5 else None
        top = sorted(crops, key=lambda c: (c[2] is None, -(c[2] or 0)))[:3]
        out.append(
            {
                "state": st,
                "district": dist,
                "latest_year": dlatest,
                "total": total,
                "top_crops": [c[0] for c in top],
                "perishable_share": (perishable / total * 100) if total else None,
                "vs_prev5_pct": ((total - prev5_avg) / prev5_avg * 100) if prev5_avg else None,
            }
        )

    states = sorted({r["state"] for r in out})
    if state:
        out = [r for r in out if r["state"] == state]
    if q:
        needle = q.strip().lower()
        out = [r for r in out if needle in r["district"].lower()]
    if sort == "name":
        out.sort(key=lambda r: (r["state"], r["district"]))
    elif sort == "perishable":
        out.sort(key=lambda r: (r["perishable_share"] is None, -(r["perishable_share"] or 0)))
    elif sort == "vs5":
        out.sort(key=lambda r: (r["vs_prev5_pct"] is None, -(r["vs_prev5_pct"] or 0)))
    else:
        out.sort(key=lambda r: -r["total"])
    return {"states": states, "rows": out, "latest_year": max(y for years in totals.values() for y in years)}


def district_detail(session: Session, state: str, district: str, crop: str = "") -> dict | None:
    """The full per-district card behind a directory tap: latest-year insight,
    year-by-year totals, per-crop table, and one crop's trend."""
    rows = session.execute(
        select(
            CropDistrictYearRollup.year_label,
            CropDistrictYearRollup.crop_name,
            CropDistrictYearRollup.crop_type,
            CropDistrictYearRollup.production_t,
            CropDistrictYearRollup.area_ha,
            CropDistrictYearRollup.yield_t_per_ha,
            CropDistrictYearRollup.basis,
        )
        .where(
            CropDistrictYearRollup.state_name == state,
            CropDistrictYearRollup.district_name == district,
        )
        .order_by(CropDistrictYearRollup.year_label)
    ).all()
    if not rows:
        return None

    by_year: dict[str, list] = defaultdict(list)
    for year, name, ctype, prod, area, yld, basis in rows:
        by_year[year].append(
            {
                "crop": name,
                "crop_type": ctype,
                # DES publishes coconut in nuts, not tonnes - the row keeps its
                # published figure but carries its real unit, and it never
                # enters tonne totals or top-crop rankings.
                "unit": NON_TONNE_CROPS.get(name, "t"),
                "production": float(prod) if prod is not None else None,
                "area": float(area) if area is not None else None,
                "yield": float(yld) if yld is not None else None,
                "basis": basis,
            }
        )
    latest = max(by_year)
    summary = sorted(
        by_year[latest],
        key=lambda r: (r["unit"] != "t", r["production"] is None, -(r["production"] or 0)),
    )
    tonne_crops = [r for r in summary if r["unit"] == "t"]
    total = sum(r["production"] or 0 for r in tonne_crops)
    perishable = sum(
        (r["production"] or 0) for r in tonne_crops if r["crop_type"] in PERISHABLE_CROP_TYPES
    )
    year_totals = {
        year: sum(r["production"] or 0 for r in crops if r["unit"] == "t")
        for year, crops in sorted(by_year.items())
    }
    prev5 = [year_totals[y] for y in sorted(year_totals) if y < latest][-5:]
    prev5_avg = sum(prev5) / len(prev5) if prev5 else None
    insight = {
        "latest_year": latest,
        "total": total,
        "n_crops": len(summary),
        "top_crops": tonne_crops[:3],
        "perishable": perishable,
        "perishable_share": (perishable / total * 100) if total else None,
        "prev5_avg": prev5_avg,
        "vs_prev5_pct": ((total - prev5_avg) / prev5_avg * 100) if prev5_avg else None,
        "year_totals": year_totals,
    }
    top_crop = (
        crop
        if crop and any(r["crop"] == crop for r in summary)
        else (tonne_crops[0]["crop"] if tonne_crops else (summary[0]["crop"] if summary else ""))
    )
    trend = [
        {"year": year, **next(r for r in crops if r["crop"] == top_crop)}
        for year, crops in sorted(by_year.items())
        if any(r["crop"] == top_crop for r in crops)
    ] if top_crop else []
    return {
        "state": state,
        "district": district,
        "insight": insight,
        "summary": summary,
        "top_crop": top_crop,
        "trend": trend,
    }


def district_index(session: Session) -> list[dict]:
    """Every district in store, with its latest published year (rollup-backed)."""
    rows = session.execute(
        select(
            CropDistrictYearRollup.state_name,
            CropDistrictYearRollup.district_name,
            func.max(CropDistrictYearRollup.year_label),
        ).group_by(CropDistrictYearRollup.state_name, CropDistrictYearRollup.district_name)
    ).all()
    return [
        {"state": state, "district": district, "latest_year": latest}
        for state, district, latest in sorted(rows, key=lambda r: (r[0], r[1]))
    ]


# ---------------------------------------------------------------------------
# Raw-row helpers (small slices of the published rows, used by tests and any
# read that must show the source rows exactly as published).
# ---------------------------------------------------------------------------


def _annualise(rows: list[CropProductionRecord]) -> dict:
    """One crop's rows for one district-year -> annual figures, no double-count.

    Total row when present, else the sum of the seasonal rows. `basis` records
    which leg produced the number, so the UI can show it. rebuild_rollup()
    applies this same rule in SQL; the two must agree.
    """
    total_row = next((r for r in rows if r.season == SEASON_TOTAL), None)
    seasonal = [r for r in rows if r.season != SEASON_TOTAL]
    if total_row is not None:
        return {
            "production": total_row.production_t,
            "area": total_row.area_ha,
            "yield": total_row.yield_t_per_ha,
            "basis": BASIS_ANNUAL,
        }
    prod = [r.production_t for r in seasonal if r.production_t is not None]
    area = [r.area_ha for r in seasonal if r.area_ha is not None]
    production = sum(prod) if prod else None
    area_sum = sum(area) if area else None
    yld = round(production / area_sum, 3) if production and area_sum else None
    return {"production": production, "area": area_sum, "yield": yld, "basis": BASIS_SEASONAL}


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
