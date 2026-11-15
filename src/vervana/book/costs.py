"""Cost stack for The Book (M17): storage, financing, outbound logistics, quality loss.

Every function is PURE and returns integer paise per kg. Every rate is a VISIBLE
ASSUMPTION loaded from `data/config/book_costs.csv` (per-commodity, with a documented
`__default__` row), never a quoted cost. The caller shows the rate alongside the figure
so a cost is always an ESTIMATE labelled with how it was computed.

RISK[R16-CARRY-ASSUMPTION]: storage (₹/kg/day) and financing (annual %) are single flat
rates. Real carrying cost varies by store, lot size, and finance line. Shown as an
estimate with the rate visible; tune in the CSV. Evidence: docs/RISK_REGISTER.md. PENDING.

RISK[R17-SPOILAGE-ASSUMPTION]: quality loss uses a flat %/day spoilage rate per commodity.
Real deterioration is non-linear and depends on grade, store, and weather. An estimate,
never a measured loss. Evidence: docs/RISK_REGISTER.md. PENDING.

RISK[R15-FREIGHT-ASSUMPTION]: outbound logistics reuses the sourcing freight estimate
(flat ₹/tonne/km over a straight-line distance). Inherited unchanged from the sourcing
layer; see config.freight_rate_per_tonne_km.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
COSTS_PATH = REPO_ROOT / "data" / "config" / "book_costs.csv"
DEFAULT_KEY = "__default__"

# Hard fallback used only if the CSV is missing its __default__ row entirely, so the
# engine never silently applies a zero cost. Documented, conservative, overridable.
_HARD_DEFAULT = ("__hard_default__", 5, 0.12, 0.5)


@dataclass(frozen=True)
class CostRates:
    """One commodity's carrying-cost assumptions. `key` is the row the rates came from
    ('__default__' or '__hard_default__' when the commodity is not listed)."""

    key: str
    storage_paise_per_kg_per_day: int
    financing_annual_pct: float
    spoilage_pct_per_day: float


@dataclass(frozen=True)
class CostLine:
    """One cost component in paise/kg, with the human-readable basis that produced it."""

    paise_per_kg: int
    basis: str


@dataclass(frozen=True)
class CostBreakdown:
    """The full per-kg carrying cost of a decision, every line labelled with its basis."""

    storage: CostLine
    financing: CostLine
    logistics: CostLine
    quality_loss: CostLine

    @property
    def total_paise_per_kg(self) -> int:
        return (
            self.storage.paise_per_kg
            + self.financing.paise_per_kg
            + self.logistics.paise_per_kg
            + self.quality_loss.paise_per_kg
        )


def load_cost_rates(commodity: str, *, path: Path = COSTS_PATH) -> CostRates:
    """Rates for `commodity`, falling back to the CSV's `__default__` row, then to the
    hard default. Never returns zero-cost silently."""
    rows: dict[str, tuple[str, int, float, float]] = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                rows[row["commodity"]] = (
                    row["commodity"],
                    int(row["storage_paise_per_kg_per_day"]),
                    float(row["financing_annual_pct"]),
                    float(row["spoilage_pct_per_day"]),
                )
    chosen = rows.get(commodity) or rows.get(DEFAULT_KEY) or _HARD_DEFAULT
    key, storage, fin, spoil = chosen
    # When the commodity itself is listed, the key is the default/hard-default marker only
    # if we fell through; otherwise mark it as the commodity's own row.
    marker = commodity if commodity in rows else key
    return CostRates(
        key=marker,
        storage_paise_per_kg_per_day=storage,
        financing_annual_pct=fin,
        spoilage_pct_per_day=spoil,
    )


def storage_cost(rates: CostRates, days: int) -> CostLine:
    paise = rates.storage_paise_per_kg_per_day * max(days, 0)
    return CostLine(
        paise,
        f"{rates.storage_paise_per_kg_per_day}p/kg/day × {max(days, 0)}d",
    )


def financing_cost(rates: CostRates, purchase_price_paise_per_kg: int, days: int) -> CostLine:
    """purchase value × annual % × days/365, on the capital tied up in the stock."""
    paise = round(
        purchase_price_paise_per_kg * rates.financing_annual_pct * max(days, 0) / 365.0
    )
    return CostLine(
        paise,
        f"{rates.financing_annual_pct:.0%}/yr on ₹{purchase_price_paise_per_kg / 100:.2f}/kg × "
        f"{max(days, 0)}d",
    )


def logistics_cost(outbound_paise_per_kg: int | None) -> CostLine:
    """Outbound freight to the destination (reused sourcing estimate). None -> 0 with the
    basis stating the distance is unknown, so a missing cost is never a hidden zero."""
    if outbound_paise_per_kg is None:
        return CostLine(0, "distance unknown — outbound freight not estimated")
    return CostLine(max(outbound_paise_per_kg, 0), "reused sourcing freight estimate (R15)")


def quality_loss_cost(
    rates: CostRates, expected_sale_price_paise_per_kg: int, days: int
) -> CostLine:
    """Spoiled fraction × the value it would have fetched. Capped at 100% of the stock."""
    frac = min(rates.spoilage_pct_per_day / 100.0 * max(days, 0), 1.0)
    paise = round(expected_sale_price_paise_per_kg * frac)
    return CostLine(
        paise,
        f"{rates.spoilage_pct_per_day:g}%/day × {max(days, 0)}d = {frac:.1%} of "
        f"₹{expected_sale_price_paise_per_kg / 100:.2f}/kg",
    )


def carrying_cost(
    *,
    rates: CostRates,
    purchase_price_paise_per_kg: int,
    expected_sale_price_paise_per_kg: int,
    days: int,
    outbound_paise_per_kg: int | None,
) -> CostBreakdown:
    """Full per-kg carrying cost of holding this lot `days` more and then selling it."""
    return CostBreakdown(
        storage=storage_cost(rates, days),
        financing=financing_cost(rates, purchase_price_paise_per_kg, days),
        logistics=logistics_cost(outbound_paise_per_kg),
        quality_loss=quality_loss_cost(rates, expected_sale_price_paise_per_kg, days),
    )


def sell_now_cost(outbound_paise_per_kg: int | None) -> CostBreakdown:
    """Cost of selling today: outbound logistics only — no storage, financing, or spoilage
    accrues when the stock leaves now."""
    return CostBreakdown(
        storage=CostLine(0, "sold today — no storage"),
        financing=CostLine(0, "sold today — no financing"),
        logistics=logistics_cost(outbound_paise_per_kg),
        quality_loss=CostLine(0, "sold today — no spoilage"),
    )
