"""Supply watch zones (M11): the districts the supply-side layer watches.

A zone ties a growing district to the commodities the platform tracks there and
gives the satellite connectors a where (district-HQ coordinates). Coordinates
are config, not code: refining a zone to a growing-belt centroid is a data
change, matching the M8 mandi-config principle. District-HQ points are a
deliberate starting approximation and say so in docs/SUPPLY.md.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ZONES_PATH = REPO_ROOT / "data" / "config" / "supply_zones.csv"


@dataclass(frozen=True)
class SupplyZone:
    zone: str
    district: str
    state: str
    lat: float
    lon: float
    commodities: list[str] = field(default_factory=list)


def load_zones(path: Path = ZONES_PATH) -> list[SupplyZone]:
    zones: list[SupplyZone] = []
    if not path.exists():
        return zones
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            zones.append(
                SupplyZone(
                    zone=row["zone"],
                    district=row["district"],
                    state=row["state"],
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    commodities=[c.strip() for c in row["commodities"].split(";") if c.strip()],
                )
            )
    return zones


def get_zone(name: str, path: Path = ZONES_PATH) -> SupplyZone | None:
    for z in load_zones(path):
        if z.zone == name:
            return z
    return None
