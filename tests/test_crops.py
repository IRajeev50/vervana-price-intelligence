"""DES/APY crop production layer: import, rollup rule, directory and detail reads.

All offline: in-memory/temp SQLite, tiny synthetic CSVs that reproduce the
traps of the real national file - Total rows that coexist with seasonal rows,
blank production cells, and district names that repeat across states.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import vervana.models  # noqa: F401 - register tables
from vervana.db.base import Base
from vervana.db.engine import make_engine, session_scope
from vervana.models.crop_production import CropDistrictYearRollup, CropProductionRecord
from vervana.repository.crop_production import (
    _annualise,
    district_detail,
    district_directory,
    import_apy_csv,
    rebuild_rollup,
)

HEADER = "id,year,state_name,state_code,district_name,district_code,crop_name,crop_code,crop_type,season,area,area_unit,production,production_unit,yield,yield_unit\n"


def _row(i, year, state, district, crop, ctype, season, area, prod, yld):
    return f"{i},{year},{state},1,{district},1,{crop},1.0,{ctype},{season},{area},Hectare,{prod},Tonnes,{yld},Tonnes/Hectare\n"


def _csv(tmp_path: Path, rows: list[str]) -> Path:
    p = tmp_path / "apy.csv"
    p.write_text(HEADER + "".join(rows), encoding="utf-8")
    return p


# Purnia 2022-2023: DES publishes a Total row AND seasonal rows for Rice -
# adding both is the 1.59M-tonne double-count mistake. Wheat is seasonal-only.
# Potato has a Total row with blank production (stays NULL, still "annual row").
# Aurangabad exists in both Bihar and Maharashtra and must not merge.
ROWS = [
    _row(1, "2022-2023", "Bihar", "Purnia", "Rice", "Cereals", "Total", 100, 125312, 1.253),
    _row(2, "2022-2023", "Bihar", "Purnia", "Rice", "Cereals", "Kharif", 60, 75000, 1.25),
    _row(3, "2022-2023", "Bihar", "Purnia", "Rice", "Cereals", "Rabi", 40, 50312, 1.258),
    _row(4, "2022-2023", "Bihar", "Purnia", "Wheat", "Cereals", "Rabi", 50, 40000, 0.8),
    _row(5, "2022-2023", "Bihar", "Purnia", "Wheat", "Cereals", "Kharif", 10, 5000, 0.5),
    _row(6, "2022-2023", "Bihar", "Purnia", "Potato", "Vegetable", "Total", "", "", ""),
    _row(7, "2021-2022", "Bihar", "Purnia", "Rice", "Cereals", "Total", 100, 100000, 1.0),
    _row(8, "2022-2023", "Maharashtra", "Aurangabad", "Cotton", "Fibre", "Total", 10, 2000, 0.2),
    _row(9, "2022-2023", "Bihar", "Aurangabad", "Rice", "Cereals", "Total", 20, 9000, 0.45),
    # DES publishes coconut in nuts; the file still labels the unit "Tonnes".
    _row(10, "2022-2023", "Bihar", "Purnia", "Coconut", "Oilseeds", "Whole Year", 100, 1500000, 15000),
    _row(11, "", "Bihar", "Purnia", "Rice", "Cereals", "Total", 1, 1, 1),  # missing year: rejected
]


@pytest.fixture
def loaded(tmp_path, session):
    path = _csv(tmp_path, ROWS)
    res = import_apy_csv(session, path)
    n = rebuild_rollup(session)
    return res, n


def test_import_counts_and_rejects(loaded):
    res, n = loaded
    assert res["added"] == 10
    assert res["rejected"] == 1
    assert n == 7  # district-year-crop groups


def test_import_idempotent(tmp_path, session):
    path = _csv(tmp_path, ROWS)
    first = import_apy_csv(session, path)
    second = import_apy_csv(session, path)
    assert first["added"] == 10
    assert second == {"added": 0, "skipped": 10, "rejected": 1, "reasons": second["reasons"]}
    assert session.scalar(select(func.count()).select_from(CropProductionRecord)) == 10


def test_rollup_never_double_counts_total_plus_seasons(loaded, session):
    row = session.execute(
        select(CropDistrictYearRollup).where(
            CropDistrictYearRollup.district_name == "Purnia",
            CropDistrictYearRollup.crop_name == "Rice",
            CropDistrictYearRollup.year_label == "2022-2023",
        )
    ).scalar_one()
    assert float(row.production_t) == 125312  # the annual row, not 125312 + 75000 + 50312
    assert row.basis == "annual row"


def test_rollup_seasonal_sum_when_no_total(loaded, session):
    row = session.execute(
        select(CropDistrictYearRollup).where(
            CropDistrictYearRollup.district_name == "Purnia",
            CropDistrictYearRollup.crop_name == "Wheat",
            CropDistrictYearRollup.year_label == "2022-2023",
        )
    ).scalar_one()
    assert float(row.production_t) == 45000
    assert float(row.area_ha) == 60
    assert float(row.yield_t_per_ha) == round(45000 / 60, 3)
    assert row.basis == "seasonal sum"


def test_rollup_total_row_with_blank_figures_stays_annual_and_null(loaded, session):
    row = session.execute(
        select(CropDistrictYearRollup).where(
            CropDistrictYearRollup.district_name == "Purnia",
            CropDistrictYearRollup.crop_name == "Potato",
            CropDistrictYearRollup.year_label == "2022-2023",
        )
    ).scalar_one()
    assert row.basis == "annual row"
    assert row.production_t is None  # a blank stays NULL, never zero-filled


def test_sql_rollup_matches_python_annualise(loaded, session):
    """The SQL rebuild and the Python reference must agree figure for figure."""
    raw = session.scalars(select(CropProductionRecord)).all()
    groups: dict[tuple, list] = {}
    for r in raw:
        groups.setdefault((r.state_name, r.district_name, r.year_label, r.crop_name), []).append(r)
    rollups = {
        (r.state_name, r.district_name, r.year_label, r.crop_name): r
        for r in session.scalars(select(CropDistrictYearRollup)).all()
    }
    assert set(groups) == set(rollups)
    for key, rows in groups.items():
        ref = _annualise(rows)
        got = rollups[key]
        assert (float(got.production_t) if got.production_t is not None else None) == (
            float(ref["production"]) if ref["production"] is not None else None
        ), key
        assert got.basis == ref["basis"], key


def test_directory_keys_by_state_and_district(loaded, session):
    data = district_directory(session)
    names = {(r["state"], r["district"]) for r in data["rows"]}
    assert ("Bihar", "Aurangabad") in names
    assert ("Maharashtra", "Aurangabad") in names
    purnia = next(r for r in data["rows"] if r["district"] == "Purnia")
    # 125312 (Rice, annual row) + 45000 (Wheat, seasonal sum) + 0 (Potato, NULL)
    # Coconut (1.5M nuts) must NOT enter the tonne total or the top-crop ranking.
    assert purnia["total"] == 170312
    assert purnia["latest_year"] == "2022-2023"
    assert purnia["top_crops"][0] == "Rice"
    assert "Coconut" not in purnia["top_crops"]
    # vs 5-yr avg: only one preceding year (2021-2022, 100000 t)
    assert purnia["vs_prev5_pct"] == pytest.approx(70.312)
    assert data["states"] == ["Bihar", "Maharashtra"]


def test_directory_filters(loaded, session):
    assert len(district_directory(session, state="Bihar")["rows"]) == 2
    assert len(district_directory(session, q="aurang")["rows"]) == 2
    assert len(district_directory(session, state="Bihar", q="purnia")["rows"]) == 1
    assert district_directory(session, q="zzz")["rows"] == []


def test_district_detail(loaded, session):
    d = district_detail(session, "Bihar", "Purnia")
    assert d["insight"]["total"] == 170312
    coconut = next(r for r in d["summary"] if r["crop"] == "Coconut")
    assert coconut["unit"] == "nuts"
    assert coconut["production"] == 1500000
    assert all(r["crop"] != "Coconut" for r in d["insight"]["top_crops"])
    assert d["insight"]["year_totals"] == {"2021-2022": 100000, "2022-2023": 170312}
    assert [r["crop"] for r in d["summary"]][:2] == ["Rice", "Wheat"]
    assert d["top_crop"] == "Rice"
    assert [t["year"] for t in d["trend"]] == ["2021-2022", "2022-2023"]
    wheat = district_detail(session, "Bihar", "Purnia", crop="Wheat")
    assert wheat["top_crop"] == "Wheat"
    assert district_detail(session, "Bihar", "Nowhere") is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "web.sqlite3"
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{db}")
    Base.metadata.create_all(make_engine(f"sqlite:///{db}"))
    path = _csv(tmp_path, ROWS)
    with session_scope() as s:
        import_apy_csv(s, path)
        rebuild_rollup(s)
    from vervana.web.app import app

    return TestClient(app)


def test_directory_page_lists_key_figures_only(client):
    r = client.get("/districts")
    assert r.status_code == 200
    assert "Purnia" in r.text
    assert "170,312" in r.text
    assert "/districts/Bihar/Purnia" in r.text
    assert "Maharashtra" in r.text
    # list shows the year per row; both Aurangabads stay separate
    assert r.text.count("Aurangabad") >= 2


def test_directory_page_filter(client):
    r = client.get("/districts", params={"state": "Maharashtra"})
    assert r.status_code == 200
    assert "Aurangabad" in r.text
    assert "Purnia" not in r.text


def test_district_detail_page(client):
    r = client.get("/districts/Bihar/Purnia")
    assert r.status_code == 200
    assert "170,312" in r.text
    assert "annual row" in r.text
    assert "seasonal sum" in r.text
    r2 = client.get("/districts/Bihar/Purnia", params={"crop": "Wheat"})
    assert r2.status_code == 200
    assert "Wheat in Purnia" in r2.text


def test_district_detail_404(client):
    assert client.get("/districts/Bihar/Nowhere").status_code == 404


def test_empty_state_hint(client, tmp_path, monkeypatch):
    monkeypatch.setenv("VERVANA_DATABASE_URL", f"sqlite:///{tmp_path / 'empty.sqlite3'}")
    Base.metadata.create_all(make_engine(f"sqlite:///{tmp_path / 'empty.sqlite3'}"))
    from vervana.web.app import app

    r = TestClient(app).get("/districts")
    assert r.status_code == 200
    assert "import-apy --national" in r.text
