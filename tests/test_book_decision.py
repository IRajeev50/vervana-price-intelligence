"""The Book decision engine: the five verdicts + the unshippable-band honesty gate (M17).

No network, no DB — the engine is pure. Every branch is forced by a synthetic scenario,
and the central honesty property (no confident forward price when the band is unshippable)
is asserted directly.
"""

from __future__ import annotations

from vervana.book.costs import carrying_cost, load_cost_rates, sell_now_cost
from vervana.book.decision import (
    ExpectedPrice,
    FloodFlag,
    RerouteAlt,
    decide,
)
from vervana.forecast.band import Band


def _validated(p50: int, *, p10: int | None = None, p90: int | None = None) -> ExpectedPrice:
    lo = p10 if p10 is not None else p50 - 100
    hi = p90 if p90 is not None else p50 + 100
    band = Band(p10=lo, p50=p50, p90=hi)
    return ExpectedPrice(
        paise_per_kg=p50,
        source="band-validated",
        shippable=True,
        reason="band cleared the kill bar",
        band=band,
    )


def _anchor(today: int) -> ExpectedPrice:
    return ExpectedPrice(
        paise_per_kg=today,
        source="anchor-fallback",
        shippable=False,
        reason="band did not clear the kill bar; today's price held flat",
        band=None,
    )


def _costs(commodity: str, *, expected: int, days: int, outbound: int | None):
    rates = load_cost_rates(commodity)
    hold = carrying_cost(
        rates=rates,
        purchase_price_paise_per_kg=1500,
        expected_sale_price_paise_per_kg=expected,
        days=days,
        outbound_paise_per_kg=outbound,
    )
    now = sell_now_cost(outbound)
    return hold, now


def test_hold_when_validated_band_beats_now_beyond_uncertainty():
    hold, now = _costs("Potato", expected=3000, days=20, outbound=100)
    d = decide(
        commodity="Potato",
        expected=_validated(3000, p10=2950, p90=3050),  # tight band -> small margin
        immediate_price_paise_per_kg=2000,
        hold_costs=hold,
        now_costs=now,
        horizon_days=20,
    )
    assert d.verdict == "HOLD"
    assert d.edge_paise_per_kg > d.uncertainty_margin_paise


def test_release_when_selling_now_beats_holding_beyond_uncertainty():
    hold, now = _costs("Potato", expected=1800, days=20, outbound=100)
    d = decide(
        commodity="Potato",
        expected=_validated(1800, p10=1750, p90=1850),
        immediate_price_paise_per_kg=2600,
        hold_costs=hold,
        now_costs=now,
        horizon_days=20,
    )
    assert d.verdict == "RELEASE"


def test_wait_when_validated_edge_is_within_band_uncertainty():
    # Wide band -> large uncertainty margin; small edge cannot clear it.
    hold, now = _costs("Potato", expected=2100, days=5, outbound=100)
    d = decide(
        commodity="Potato",
        expected=_validated(2100, p10=1600, p90=2600),  # ±500 uncertainty
        immediate_price_paise_per_kg=2050,
        hold_costs=hold,
        now_costs=now,
        horizon_days=5,
    )
    assert d.verdict == "WAIT"


def test_unshippable_band_forces_wait_and_never_a_confident_forward_price():
    # THE HONESTY GATE: band did not clear the kill bar -> WAIT, anchor fallback labelled,
    # and no HOLD/RELEASE is issued however the carry math looks.
    hold, now = _costs("Potato", expected=2000, days=30, outbound=100)
    d = decide(
        commodity="Potato",
        expected=_anchor(2000),
        immediate_price_paise_per_kg=2000,
        hold_costs=hold,
        now_costs=now,
        horizon_days=30,
    )
    assert d.verdict == "WAIT"
    assert any("no validated forward price" in u for u in d.uncertainties)
    assert any("kill bar" in s or "expected sale price" in s for s in d.invalidated_if)
    # The carry cost is still surfaced as information, just not acted on.
    assert "flat-price assumption" in d.why


def test_reroute_when_alternative_destination_is_materially_better():
    hold, now = _costs("Onion", expected=2000, days=10, outbound=100)
    d = decide(
        commodity="Onion",
        expected=_validated(2000, p10=1950, p90=2050),
        immediate_price_paise_per_kg=2000,
        hold_costs=hold,
        now_costs=now,
        horizon_days=10,
        reroute=RerouteAlt(
            market="Lasalgaon", net_paise_per_kg=2600, reason="lower landed cost"
        ),
    )
    assert d.verdict == "REROUTE"
    assert "Lasalgaon" in d.why


def test_flood_on_destination_reroutes_to_a_safe_alternative():
    hold, now = _costs("Onion", expected=2000, days=10, outbound=100)
    d = decide(
        commodity="Onion",
        expected=_anchor(2000),  # even without a validated band, flood reroute is allowed
        immediate_price_paise_per_kg=2000,
        hold_costs=hold,
        now_costs=now,
        horizon_days=10,
        flood=FloodFlag(zone="delhi-yamuna", severity="SEVERE", is_risk=True),
        reroute=RerouteAlt(
            market="Pune", net_paise_per_kg=1950, reason="safe inland destination", flood_safe=True
        ),
    )
    assert d.verdict == "REROUTE"
    assert "flood-exposed" in d.why
    assert any("delhi-yamuna" in u for u in d.uncertainties)


def test_flood_without_safe_alternative_flags_but_does_not_fabricate_a_reroute():
    hold, now = _costs("Onion", expected=2050, days=10, outbound=100)
    d = decide(
        commodity="Onion",
        expected=_validated(2050, p10=2000, p90=2100),
        immediate_price_paise_per_kg=2000,
        hold_costs=hold,
        now_costs=now,
        horizon_days=10,
        flood=FloodFlag(zone="delhi-yamuna", severity="ABOVE_NORMAL", is_risk=True),
        reroute=None,
    )
    assert d.verdict != "REROUTE"  # no alternative -> no invented reroute
    assert any("delhi-yamuna" in u for u in d.uncertainties)


def test_every_decision_exposes_all_five_rationale_fields():
    hold, now = _costs("Potato", expected=2000, days=10, outbound=100)
    d = decide(
        commodity="Potato",
        expected=_anchor(2000),
        immediate_price_paise_per_kg=2000,
        hold_costs=hold,
        now_costs=now,
        horizon_days=10,
    )
    assert d.why
    assert d.evidence and d.assumptions and d.uncertainties and d.invalidated_if
