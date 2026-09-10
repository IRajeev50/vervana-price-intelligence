"""Crop profiles and honest forecast horizons (M9).

The horizon rule comes from the crop's biology, not from model ambition:
an upstream-signal outlook can honestly reach about (crop duration + storage
buffer) ahead. Sugarcane is a 10-18 month crop decided by the June-Sep monsoon,
so 6-8 months of lead is defensible; a tomato's is 4-8 weeks and the platform
says so. Profiles are config (data/config/crop_profiles.csv), not code: adding
a commodity is a data change, matching the M8 mandi-config principle.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROFILES_PATH = REPO_ROOT / "data" / "config" / "crop_profiles.csv"

# Fallback for any commodity without a profile: assume a short-cycle perishable.
DEFAULT_CYCLE_MONTHS = (1.0, 2.0)
DEFAULT_STORAGE_WEEKS = 0.0


@dataclass
class CropProfile:
    commodity: str
    cycle_months_min: float
    cycle_months_max: float
    storage_buffer_weeks: float
    horizon_days_min: int
    horizon_days_max: int
    primary_regions: list[str] = field(default_factory=list)
    horizon_note: str = ""


@dataclass
class Horizon:
    commodity: str
    min_days: int
    max_days: int
    label: str
    basis: str  # the reasoning, shown next to the number


def load_profiles(path: Path = PROFILES_PATH) -> dict[str, CropProfile]:
    profiles: dict[str, CropProfile] = {}
    if not path.exists():
        return profiles
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            profiles[row["commodity"]] = CropProfile(
                commodity=row["commodity"],
                cycle_months_min=float(row["cycle_months_min"]),
                cycle_months_max=float(row["cycle_months_max"]),
                storage_buffer_weeks=float(row["storage_buffer_weeks"]),
                horizon_days_min=int(row["horizon_days_min"]),
                horizon_days_max=int(row["horizon_days_max"]),
                primary_regions=[r.strip() for r in row["primary_regions"].split(";") if r.strip()],
                horizon_note=row["horizon_note"],
            )
    return profiles


def get_profile(commodity: str, path: Path = PROFILES_PATH) -> CropProfile:
    profiles = load_profiles(path)
    if commodity in profiles:
        return profiles[commodity]
    return CropProfile(
        commodity=commodity,
        cycle_months_min=DEFAULT_CYCLE_MONTHS[0],
        cycle_months_max=DEFAULT_CYCLE_MONTHS[1],
        storage_buffer_weeks=DEFAULT_STORAGE_WEEKS,
        horizon_days_min=28,
        horizon_days_max=56,
        horizon_note="no profile on record - treated as a short-cycle perishable (fail closed)",
    )


def forecast_horizon(profile: CropProfile) -> Horizon:
    """The honest outlook horizon, in days, from the crop profile config.

    The horizon is set per crop in data/config/crop_profiles.csv from the crop's
    duration and storage economics (a signal can only lead the price by as long
    as supply is both undecided and storable); it is never derived from model
    ambition. The basis string shows the cycle/storage numbers behind it.
    """
    min_days = profile.horizon_days_min
    max_days = profile.horizon_days_max
    if max_days <= 75:
        label = f"{max(1, min_days // 7)}-{max(1, max_days // 7)} weeks"
    else:
        label = f"{min_days // 30}-{max_days // 30} months"
    basis = (
        f"crop cycle {profile.cycle_months_min:g}-{profile.cycle_months_max:g} months "
        f"+ {profile.storage_buffer_weeks:g} weeks storage buffer. {profile.horizon_note}"
    ).strip()
    return Horizon(
        commodity=profile.commodity,
        min_days=min_days,
        max_days=max_days,
        label=label,
        basis=basis,
    )
