"""The decision engine for The Book (M17): net realisation -> advisory verdict.

PURE and fully testable: the repository/CLI/web layer fetches prices, bands, overlays,
and reroute alternatives from the store and passes plain values in; this module decides.

The five verdicts:
  * HOLD    - validated band says expected realisation beats selling now by more than the
              band's own uncertainty.
  * RELEASE - validated band says selling now beats holding by more than that uncertainty.
  * WAIT    - the edge is inside the uncertainty band, OR there is no validated forward
              price at all (the honest default: we will not issue a HOLD/RELEASE off a
              forward price the kill bar rejected).
  * REROUTE - a different destination has a materially better net landed realisation, OR
              the intended destination carries a riverine flood overlay and a safe
              alternative exists. A risk/cost action, allowed even without a validated band.

THE HONESTY GATE: expected sale price is the forecast band p50 ONLY where that commodity's
band cleared the kill bar (`shippable`). Otherwise it falls back to today's price held flat
("anchor fallback"), the decision is forced to WAIT, and the output says so. The Book never
invents a confident forward price where the band failed - it inherits RISK[R7]/R13.

Flood overlays are riverine tail-risk flags on REROUTE/RELEASE reasoning, NEVER a price
input and never a band feature.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vervana.forecast.band import Band

# A reroute only wins if it beats the best on-hand option by at least this margin (on top
# of the band's own uncertainty), so tiny freight differences never trigger a move.
REROUTE_MATERIAL_PAISE = 50  # ₹0.50/kg


@dataclass(frozen=True)
class ExpectedPrice:
    """The expected sale price fed into the hold calculation, and where it came from."""

    paise_per_kg: int
    source: str  # "band-validated" | "anchor-fallback"
    shippable: bool  # did the commodity's band clear the kill bar?
    reason: str
    band: Band | None = None


@dataclass(frozen=True)
class RerouteAlt:
    """A candidate alternative destination and its expected net landed realisation."""

    market: str
    net_paise_per_kg: int
    reason: str
    flood_safe: bool = True


@dataclass(frozen=True)
class FloodFlag:
    """The intended destination's riverine flood overlay, reduced to what the decision
    needs. `is_risk` is True for ABOVE_NORMAL/SEVERE/EXTREME."""

    zone: str
    severity: str
    is_risk: bool


@dataclass(frozen=True)
class BookDecision:
    verdict: str  # HOLD | RELEASE | WAIT | REROUTE
    why: str
    evidence: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    invalidated_if: list[str] = field(default_factory=list)
    net_hold_paise_per_kg: int = 0
    net_now_paise_per_kg: int = 0
    edge_paise_per_kg: int = 0
    uncertainty_margin_paise: int = 0


def _r(paise: float) -> str:
    return f"₹{paise / 100:.2f}/kg"


def _uncertainty_margin(expected: ExpectedPrice) -> int:
    """Half the 80% band width: the edge must clear this to justify acting. Zero with no
    band (anchor fallback forces WAIT regardless, so the value is not used to act)."""
    if expected.band is None:
        return 0
    return round((expected.band.p90 - expected.band.p10) / 2)


def decide(
    *,
    commodity: str,
    expected: ExpectedPrice,
    immediate_price_paise_per_kg: int,
    hold_costs,  # CostBreakdown
    now_costs,  # CostBreakdown
    horizon_days: int,
    flood: FloodFlag | None = None,
    reroute: RerouteAlt | None = None,
) -> BookDecision:
    """Decide HOLD/RELEASE/WAIT/REROUTE for one lot. See module docstring for the gate."""
    net_hold = expected.paise_per_kg - hold_costs.total_paise_per_kg
    net_now = immediate_price_paise_per_kg - now_costs.total_paise_per_kg
    edge = net_hold - net_now
    margin = _uncertainty_margin(expected)
    best_onhand = max(net_hold, net_now) if expected.shippable else net_now

    evidence = [
        f"expected sale {_r(expected.paise_per_kg)} ({expected.source}: {expected.reason})",
        f"immediate executable price {_r(immediate_price_paise_per_kg)}",
        f"net if held {horizon_days}d {_r(net_hold)} vs net if sold now {_r(net_now)}",
        f"carrying cost {_r(hold_costs.total_paise_per_kg)}: "
        f"storage {hold_costs.storage.basis}; financing {hold_costs.financing.basis}; "
        f"logistics {hold_costs.logistics.basis}; quality {hold_costs.quality_loss.basis}",
    ]
    assumptions = [
        f"storage {hold_costs.storage.basis}",
        f"financing {hold_costs.financing.basis}",
        f"outbound logistics: {hold_costs.logistics.basis}",
        f"quality loss {hold_costs.quality_loss.basis}",
    ]
    uncertainties: list[str] = []
    invalidated_if = [
        "a fresh executable price print moves the immediate or expected price",
        "any carrying-cost rate in data/config/book_costs.csv is revised",
    ]

    if flood is not None and flood.is_risk:
        uncertainties.append(
            f"riverine flood overlay on destination zone '{flood.zone}' "
            f"({flood.severity}) — tail-risk to logistics, NOT priced in"
        )
        invalidated_if.append(
            f"the flood overlay on '{flood.zone}' clears or worsens (riverine only)"
        )

    def _mk(verdict: str, why: str) -> BookDecision:
        return BookDecision(
            verdict=verdict,
            why=why,
            evidence=evidence,
            assumptions=assumptions,
            uncertainties=uncertainties,
            invalidated_if=invalidated_if,
            net_hold_paise_per_kg=net_hold,
            net_now_paise_per_kg=net_now,
            edge_paise_per_kg=edge,
            uncertainty_margin_paise=margin,
        )

    # 1. Flood-driven REROUTE: move away from a flood-exposed destination to a safe
    #    alternative that is at least as good as selling now.
    if (
        flood is not None
        and flood.is_risk
        and reroute is not None
        and reroute.flood_safe
        and reroute.net_paise_per_kg >= net_now
    ):
        evidence.append(f"reroute to {reroute.market}: net {_r(reroute.net_paise_per_kg)}")
        return _mk(
            "REROUTE",
            f"intended destination zone '{flood.zone}' is flood-exposed ({flood.severity}); "
            f"{reroute.market} is a non-exposed destination at {_r(reroute.net_paise_per_kg)} "
            f"net ({reroute.reason}) — move to cut riverine exposure.",
        )

    # 2. Cost-driven REROUTE: a destination beats the best on-hand option by a material
    #    margin (on top of band uncertainty).
    if reroute is not None and reroute.net_paise_per_kg - best_onhand > max(
        REROUTE_MATERIAL_PAISE, margin
    ):
        evidence.append(f"reroute to {reroute.market}: net {_r(reroute.net_paise_per_kg)}")
        return _mk(
            "REROUTE",
            f"{reroute.market} nets {_r(reroute.net_paise_per_kg)} vs best on-hand "
            f"{_r(best_onhand)} ({reroute.reason}) — materially better landed realisation.",
        )

    # 3. Anchor fallback: no validated forward price -> refuse a price-edge action.
    if not expected.shippable:
        uncertainties.append(
            "no validated forward price (band did not clear the kill bar); expected price is "
            "today's price held FLAT — the hold figure rests entirely on that assumption"
        )
        invalidated_if.append(
            f"{commodity}'s band clears the kill bar (M20 weather features) or you enter an "
            "expected sale price for this lot"
        )
        return _mk(
            "WAIT",
            f"No validated forward price for {commodity}. On a flat-price assumption, "
            f"holding {horizon_days}d costs {_r(hold_costs.total_paise_per_kg)} in carry — "
            "but we will not issue a HOLD or RELEASE off an unvalidated forward price. "
            "Decision gated pending a validated band or your expected sale price.",
        )

    # 4. Validated band: act on the edge vs the band's own uncertainty.
    uncertainties.append(
        f"band 80% interval {_r(expected.band.p10)}–{_r(expected.band.p90)}; "
        f"edge must exceed ±{_r(margin)} to act"
    )
    if edge > margin:
        return _mk(
            "HOLD",
            f"Holding {horizon_days}d nets {_r(net_hold)} vs {_r(net_now)} now — a "
            f"{_r(edge)} edge, beyond the ±{_r(margin)} band uncertainty.",
        )
    if edge < -margin:
        return _mk(
            "RELEASE",
            f"Selling now nets {_r(net_now)} vs {_r(net_hold)} if held — holding loses "
            f"{_r(-edge)}, beyond the ±{_r(margin)} band uncertainty.",
        )
    return _mk(
        "WAIT",
        f"Hold vs sell-now edge {_r(edge)} is within the ±{_r(margin)} band uncertainty — "
        "no distinguishable advantage either way.",
    )
