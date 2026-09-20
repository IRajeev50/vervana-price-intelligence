"""Aspirational Districts layer: import idempotency, provenance, and the reads.

All offline: in-memory SQLite. One test loads the real bundled seed to guard
the official count (112 districts / 27 states); the rest use tiny synthetic
CSVs to exercise the logic. No KPI scores are produced anywhere - the layer is
membership + framework only (RISK[R14]).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

import vervana.models  # noqa: F401 - register tables
from vervana.db.base import Base
from vervana.db.engine import make_engine, session_scope
from vervana.models.aspirational import AspirationalDistrict
from vervana.models.crop_production import CropDistrictYearRollup
from vervana.repository.aspirational import (
    import_seed,
    listing,
    normalise_district,
    overview,
)

REAL_SEED = Path(__file__).resolve().parent.parent / "data" / "seed" / "aspirational_districts.csv"


def _csv(tmp_path: Path, rows: list[tuple[int, str, str]]) -> Path:
    p = tmp_path / "adp.csv"
    lines = ["sno,state,district"]
    lines += [f"{sno},{state},{district}" for sno, state, district in rows]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_import_is_idempotent_and_provenanced(session, tmp_path):
    path = _csv(tmp_path, [(1, "Bihar", "Gaya"), (2, "Gujarat", "Dahod")])
    r1 = import_seed(session, path)
    assert r1 == {"added": 2, "updated": 0, "total_in_file": 2}
    # Every row carries a non-empty official source - provenance is a constraint.
    for d in session.scalars(select(AspirationalDistrict)):
        assert d.source_url.startswith("https://")
        assert d.source_name
        assert d.district_key == normalise_district(d.district_name)
    # Re-running adds nothing.
    r2 = import_seed(session, path)
    assert r2["added"] == 0
    assert session.scalar(select(func.count()).select_from(AspirationalDistrict)) == 2


def test_overview_counts_and_by_state_sorted(session, tmp_path):
    path = _csv(
        tmp_path,
        [(1, "Bihar", "Gaya"), (2, "Bihar", "Banka"), (3, "Gujarat", "Dahod")],
    )
    import_seed(session, path)
    ov = overview(session)
    assert ov["total"] == 3
    assert ov["states"] == 2
    # Sorted by count desc: Bihar (2) before Gujarat (1).
    assert ov["by_state"][0] == {"state": "Bihar", "count": 2}
    assert ov["max_state_count"] == 2
    # Framework is present but weight-free; no scores anywhere.
    assert len(ov["themes"]) == 5
    assert any(t["agri"] for t in ov["themes"])
    assert ov["n_indicators"] == 49


def test_overlap_joins_to_crop_production_by_normalised_name(session, tmp_path):
    import_seed(session, _csv(tmp_path, [(1, "Gujarat", "Dahod"), (2, "Bihar", "Gaya")]))
    # Only Dahod has production data - and with different casing/spacing.
    session.add(
        CropDistrictYearRollup(
            state_name="Gujarat",
            district_name="  DAHOD ",
            year_label="2022-2023",
            crop_name="Maize",
            crop_type="Cereal",
            production_t=1000,
            basis="annual row",
        )
    )
    session.flush()
    ov = overview(session)
    assert ov["have_production_layer"] is True
    assert ov["covered"] == 1
    rows = {r["district"]: r["has_production"] for r in listing(session)}
    assert rows["Dahod"] is True
    assert rows["Gaya"] is False


def test_real_seed_has_the_official_112(tmp_path):
    """Guard the bundled seed against silent edits: 112 districts, 27 states/UTs."""
    url = f"sqlite:///{tmp_path / 'adp.sqlite3'}"
    Base.metadata.create_all(make_engine(url))
    with session_scope() as s:
        res = import_seed(s, REAL_SEED)
        assert res["total_in_file"] == 112
        ov = overview(s)
    assert ov["total"] == 112
    assert ov["states"] == 27


def test_web_page_renders_and_stays_honest(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'web.sqlite3'}"
    monkeypatch.setenv("VERVANA_DATABASE_URL", url)
    Base.metadata.create_all(make_engine(url))
    with session_scope() as s:
        import_seed(s, REAL_SEED)
    from vervana.web.app import app

    r = TestClient(app).get("/aspirational")
    assert r.status_code == 200
    assert "Aspirational India" in r.text
    # The honesty contract must be on the page, not just in code.
    assert "RISK[R14]" in r.text
    assert "GODL-India" in r.text
