"""Read/write model for the Aspirational Districts layer.

Import is idempotent (upsert on state x district). Reads answer three honest
questions and no more:

  * how many districts, across how many states, are on the official list;
  * how that membership is distributed by state (the one chart with real,
    fully-sourced numbers);
  * which Aspirational Districts we already hold official crop-production data
    for - the join that makes the layer useful here.

No KPI scores, ranks or performance figures are produced anywhere: NITI does
not publish them as an open licensed feed and we do not invent them (RISK[R14]).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.models.aspirational import AspirationalDistrict
from vervana.models.crop_production import CropDistrictYearRollup
from vervana.time import now_utc

# Provenance for every row imported from the bundled seed. The seed is a faithful
# transcription of NITI Aayog's official "List of 112 Aspirational Districts".
SOURCE_NAME = "NITI Aayog - List of 112 Aspirational Districts"
SOURCE_URL = (
    "https://www.niti.gov.in/sites/default/files/2023-07/"
    "List-of-112-Aspirational-Districts%20(1).pdf"
)

# The published thematic framework. Indicator/data-point counts are widely and
# consistently reported by NITI; per-theme composite WEIGHTS are intentionally
# omitted - secondary sources disagree (15% vs 20% for some themes) and this
# platform does not assert a number it cannot verify against a primary source.
THEMES: list[dict] = [
    {
        "name": "Health & Nutrition",
        "blurb": "Institutional deliveries, immunisation, stunting, anaemia.",
        "agri": False,
    },
    {
        "name": "Education",
        "blurb": "Learning outcomes, transition rates, infrastructure.",
        "agri": False,
    },
    {
        "name": "Agriculture & Water Resources",
        "blurb": "Micro-irrigation, soil health cards, e-marketplace linkage, produce.",
        "agri": True,
    },
    {
        "name": "Financial Inclusion & Skill Development",
        "blurb": "Bank accounts, institutional credit, skilling placements.",
        "agri": False,
    },
    {
        "name": "Basic Infrastructure",
        "blurb": "Rural roads, household electricity, drinking water, sanitation.",
        "agri": False,
    },
]
N_INDICATORS = 49
N_DATA_POINTS = 81


def normalise_district(name: str) -> str:
    """Lower-case and strip punctuation/whitespace for cross-layer joins."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def import_seed(session: Session, path: Path) -> dict:
    """Import the official district list, idempotently. Returns a small report."""
    existing = {
        (d.state_name, d.district_name): d for d in session.scalars(select(AspirationalDistrict))
    }
    added = updated = 0
    seen: set[tuple[str, str]] = set()
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            state = (row.get("state") or "").strip()
            district = (row.get("district") or "").strip()
            sno_raw = (row.get("sno") or "").strip()
            if not state or not district or not sno_raw:
                continue
            key = (state, district)
            seen.add(key)
            sno = int(sno_raw)
            dkey = normalise_district(district)
            found = existing.get(key)
            if found is None:
                session.add(
                    AspirationalDistrict(
                        sno=sno,
                        state_name=state,
                        district_name=district,
                        district_key=dkey,
                        source_name=SOURCE_NAME,
                        source_url=SOURCE_URL,
                        imported_at=now_utc(),
                    )
                )
                added += 1
            else:
                if (found.sno, found.district_key) != (sno, dkey):
                    found.sno = sno
                    found.district_key = dkey
                    updated += 1
    session.flush()
    return {"added": added, "updated": updated, "total_in_file": len(seen)}


def _production_district_keys(session: Session) -> set[str]:
    """Normalised keys of every district we hold official crop-production data for."""
    keys: set[str] = set()
    for name in session.scalars(select(CropDistrictYearRollup.district_name).distinct()):
        keys.add(normalise_district(name))
    return keys


def overview(session: Session) -> dict:
    """Headline counts + the by-state distribution + coverage overlap."""
    rows = list(session.scalars(select(AspirationalDistrict).order_by(AspirationalDistrict.sno)))
    total = len(rows)
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r.state_name] = by_state.get(r.state_name, 0) + 1
    by_state_sorted = sorted(by_state.items(), key=lambda kv: (-kv[1], kv[0]))

    prod_keys = _production_district_keys(session)
    covered = sum(1 for r in rows if r.district_key in prod_keys) if prod_keys else 0

    return {
        "total": total,
        "states": len(by_state),
        "by_state": [{"state": s, "count": c} for s, c in by_state_sorted],
        "max_state_count": by_state_sorted[0][1] if by_state_sorted else 0,
        "covered": covered,
        "have_production_layer": bool(prod_keys),
        "themes": THEMES,
        "n_indicators": N_INDICATORS,
        "n_data_points": N_DATA_POINTS,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
    }


def listing(session: Session, state: str = "") -> list[dict]:
    """The full list (optionally one state), each row flagged for data coverage."""
    stmt = select(AspirationalDistrict).order_by(
        AspirationalDistrict.state_name, AspirationalDistrict.district_name
    )
    if state:
        stmt = stmt.where(AspirationalDistrict.state_name == state)
    prod_keys = _production_district_keys(session)
    out = []
    for r in session.scalars(stmt):
        out.append(
            {
                "sno": r.sno,
                "state": r.state_name,
                "district": r.district_name,
                "has_production": r.district_key in prod_keys,
            }
        )
    return out


def aspirational_keys(session: Session) -> set[str]:
    """Normalised district keys on the ADP list - for badging other layers."""
    return {
        normalise_district(n) for n in session.scalars(select(AspirationalDistrict.district_name))
    }
