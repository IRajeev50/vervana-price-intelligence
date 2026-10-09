"""Weather localities: the points we poll WeatherUnion for.

Coordinates are config, not code (same principle as supply_zones.csv). They are
APPROXIMATE mandi-gate points - WeatherUnion snaps a lat/long to its nearest
station, so a reading represents that nearest station's locality, not the exact
mandi. Refining a point is a data change, never a code change.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LOCALITIES_PATH = REPO_ROOT / "data" / "config" / "weather_localities.csv"


@dataclass(frozen=True)
class WeatherLocality:
    name: str
    city: str
    state: str
    lat: float
    lon: float
    note: str = ""


def load_localities(path: Path = LOCALITIES_PATH) -> list[WeatherLocality]:
    localities: list[WeatherLocality] = []
    if not path.exists():
        return localities
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            localities.append(
                WeatherLocality(
                    name=row["name"].strip(),
                    city=row.get("city", "").strip(),
                    state=row.get("state", "").strip(),
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    note=row.get("note", "").strip(),
                )
            )
    return localities
