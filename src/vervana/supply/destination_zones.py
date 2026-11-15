"""Destination (consumption-hub) flood zones (M19): where a held lot is *sold*, not grown.

Flood Hub (M15) is riverine-only; a destination zone ties a consumption hub near a river
corridor (e.g. the Yamuna at Delhi) to the markets it covers and a gauge search area for
when API access lands. This is kept SEPARATE from `supply_zones.csv` (origin growing belts,
which carry commodities) so the two concepts never blur: an origin belt predicts supply, a
destination zone flags logistics tail-risk to an outbound lot.

Coordinates and the gauge-area radius are CONFIG, not code (the M8/M11 principle), and are
deliberate approximations of the corridor, documented in docs/SUPPLY.md. The zone carries no
severity of its own — that comes only from a recorded or fetched flood overlay, never here.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEST_ZONES_PATH = REPO_ROOT / "data" / "config" / "destination_zones.csv"


@dataclass(frozen=True)
class DestinationZone:
    zone: str
    name: str
    lat: float
    lon: float
    gauge_area_radius_km: float
    markets: list[str] = field(default_factory=list)


def load_destination_zones(path: Path = DEST_ZONES_PATH) -> list[DestinationZone]:
    zones: list[DestinationZone] = []
    if not path.exists():
        return zones
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            zones.append(
                DestinationZone(
                    zone=row["zone"].strip(),
                    name=row["name"].strip(),
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    gauge_area_radius_km=float(row["gauge_area_radius_km"]),
                    markets=[m.strip() for m in row["markets"].split(";") if m.strip()],
                )
            )
    return zones


def zone_for_market(
    market_name: str, path: Path = DEST_ZONES_PATH
) -> DestinationZone | None:
    """The destination zone a market belongs to, or None when it maps to no zone.

    None is honest: a market with no mapped destination zone yields no flood flag, which is
    distinct from a market whose zone has no overlay yet (access pending).
    """
    if not market_name:
        return None
    for z in load_destination_zones(path):
        if market_name in z.markets:
            return z
    return None
