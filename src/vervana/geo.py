"""Coarse geography for the sourcing layer: state centroids + great-circle km.

Landed-cost ranking needs a distance between the buyer and each sourcing mandi.
Exact market coordinates are not populated yet (Market.latitude/longitude exist
but are mostly blank), so this module provides an HONEST APPROXIMATION: the
great-circle distance between state centroids. It is deliberately labelled as a
state-level estimate wherever it surfaces - within one state it reads as ~0 km,
which is a known limitation to refine with district/market coordinates later.

The centroids are real, verifiable geographic points (approximate geometric
centre of each state/UT), not business data - so bundling them invents nothing.
"""

from __future__ import annotations

import math

# Approximate geometric centre of each state/UT (lat, lon). Public geographic fact.
STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "Andhra Pradesh": (15.9, 79.7),
    "Arunachal Pradesh": (28.2, 94.7),
    "Assam": (26.2, 92.9),
    "Bihar": (25.6, 85.1),
    "Chhattisgarh": (21.3, 81.9),
    "Goa": (15.4, 74.0),
    "Gujarat": (22.7, 71.5),
    "Haryana": (29.2, 76.3),
    "Himachal Pradesh": (31.9, 77.2),
    "Jharkhand": (23.6, 85.3),
    "Karnataka": (15.3, 75.7),
    "Kerala": (10.5, 76.2),
    "Madhya Pradesh": (23.5, 78.5),
    "Maharashtra": (19.7, 75.7),
    "Manipur": (24.7, 93.9),
    "Meghalaya": (25.5, 91.4),
    "Mizoram": (23.2, 92.9),
    "Nagaland": (26.2, 94.5),
    "Odisha": (20.9, 85.1),
    "Punjab": (31.1, 75.3),
    "Rajasthan": (27.0, 74.2),
    "Sikkim": (27.5, 88.5),
    "Tamil Nadu": (11.1, 78.7),
    "Telangana": (17.9, 79.6),
    "Tripura": (23.9, 91.7),
    "Uttar Pradesh": (27.0, 80.9),
    "Uttarakhand": (30.1, 79.3),
    "West Bengal": (22.9, 87.9),
    "Delhi": (28.6, 77.2),
    "Jammu & Kashmir": (33.8, 76.6),
    "Ladakh": (34.2, 77.6),
    "Puducherry": (11.9, 79.8),
    "Chandigarh": (30.7, 76.8),
    "Andaman & Nicobar": (11.7, 92.7),
    "Dadra & Nagar Haveli and Daman & Diu": (20.3, 73.0),
    "Lakshadweep": (10.6, 72.6),
}

# Common Agmarknet / registry spellings that differ from the keys above.
_STATE_ALIASES: dict[str, str] = {
    "orissa": "Odisha",
    "pondicherry": "Puducherry",
    "jammu and kashmir": "Jammu & Kashmir",
    "nct of delhi": "Delhi",
    "delhi (nct)": "Delhi",
    "uttaranchal": "Uttarakhand",
    "chattisgarh": "Chhattisgarh",
    "andaman and nicobar islands": "Andaman & Nicobar",
    "andaman & nicobar islands": "Andaman & Nicobar",
    "dadra and nagar haveli": "Dadra & Nagar Haveli and Daman & Diu",
    "daman and diu": "Dadra & Nagar Haveli and Daman & Diu",
}


def canonical_state(name: str | None) -> str | None:
    """Resolve a state name to a STATE_CENTROIDS key, or None if unknown."""
    if not name:
        return None
    key = name.strip()
    if key in STATE_CENTROIDS:
        return key
    return _STATE_ALIASES.get(key.lower())


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def state_distance_km(from_state: str | None, to_state: str | None) -> float | None:
    """Approximate km between two states' centroids; None if either is unknown.

    Same state -> 0.0 (a deliberate coarse floor; refine with finer coordinates).
    """
    a, b = canonical_state(from_state), canonical_state(to_state)
    if a is None or b is None:
        return None
    if a == b:
        return 0.0
    return round(haversine_km(STATE_CENTROIDS[a], STATE_CENTROIDS[b]), 1)


def states() -> list[str]:
    """Sorted list of known states/UTs, for a buyer-location dropdown."""
    return sorted(STATE_CENTROIDS)
