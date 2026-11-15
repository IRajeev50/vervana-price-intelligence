"""M18: belt config + market-coordinate wiring (the access-free half of the experiment).

All offline. Proves the real `data/config/*.csv` belts load and that `apply_market_coords`
sets coordinates idempotently, skips unknown markets, and overwrites cleanly — the wiring
that turns the Book's "distance unknown" into a real freight estimate.
"""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.models.entities import Market
from vervana.repository.registry import apply_market_coords
from vervana.supply.zones import load_zones

REPO_ROOT = Path(__file__).resolve().parent.parent
COORDS_PATH = REPO_ROOT / "data" / "config" / "market_coords.csv"


# --- belts ----------------------------------------------------------------

def test_capsicum_and_onion_now_have_evidenced_belts():
    zones = load_zones()
    by_commodity: dict[str, list] = {}
    for z in zones:
        for c in z.commodities:
            by_commodity.setdefault(c, []).append(z)
    # Onion kept Nashik + Indore and gained the Karnataka belt its profile claimed.
    onion_states = {z.state for z in by_commodity["Onion"]}
    assert {"Maharashtra", "Madhya Pradesh", "Karnataka"} <= onion_states
    # Capsicum had NO belt before M18; now has the two evidenced ones.
    caps = by_commodity["Capsicum"]
    assert len(caps) >= 2
    assert {"Himachal Pradesh", "Karnataka"} <= {z.state for z in caps}
    # Every belt carries a real coordinate.
    for z in by_commodity["Onion"] + caps:
        assert -90 <= z.lat <= 90 and -180 <= z.lon <= 180


# --- market coordinate config ---------------------------------------------

def test_market_coords_config_is_well_formed():
    rows = list(csv.DictReader(COORDS_PATH.open(encoding="utf-8")))
    assert rows, "coords config must not be empty"
    for r in rows:
        assert r["canonical_name"].strip()
        assert -90 <= float(r["latitude"]) <= 90
        assert -180 <= float(r["longitude"]) <= 180
        assert r["source"].strip(), "every coordinate carries provenance"


def _market(session: Session, name: str, state: str = "X") -> Market:
    m = Market(canonical_name=name, city=name, state=state)
    session.add(m)
    session.flush()
    return m


def test_apply_market_coords_sets_updates_and_skips_missing(session: Session):
    # Two of the three config names exist in the registry; one does not.
    _market(session, "Azadpur", "Delhi")
    _market(session, "Gadag APMC", "Karnataka")

    res = apply_market_coords(session, COORDS_PATH)
    assert res["updated"] == 2
    assert res["unchanged"] == 0
    # Every config name without a matching market is reported, never silently dropped.
    assert "Nashik" in res["missing"]

    gadag = session.scalar(
        select(Market).where(Market.canonical_name == "Gadag APMC")
    )
    assert gadag.latitude is not None and gadag.longitude is not None


def test_apply_market_coords_is_idempotent(session: Session):
    _market(session, "Azadpur", "Delhi")
    first = apply_market_coords(session, COORDS_PATH)
    assert first["updated"] == 1

    second = apply_market_coords(session, COORDS_PATH)
    # Re-running changes nothing: same values -> unchanged, not re-written.
    assert second["updated"] == 0
    assert second["unchanged"] == 1
