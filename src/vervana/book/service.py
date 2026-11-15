"""DB-side composition for The Book (M17): turn a stored lot into a decision.

This is the only Book layer that touches the store. It fetches the executable price, the
band (validated or baseline), outbound freight, and reroute candidates, then hands plain
values to the pure `decision.decide`. Kept thin so the honest logic stays in the tested
pure core.

Not covered here yet (honest, deferred): the DESTINATION flood flag. Flood overlays are
currently keyed to ORIGIN belts (supply_zones.csv has no destination zones until M19), and
there is no market->zone map, so `decide_for_lot` passes flood=None and the UI says the
destination flood tie-in is pending M19. The engine already supports and tests the flood
path; only the data wiring waits.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from vervana.book.costs import carrying_cost, load_cost_rates, sell_now_cost
from vervana.book.decision import BookDecision, ExpectedPrice, RerouteAlt, decide
from vervana.config import get_settings
from vervana.forecast.band import conformal_band, quantile_gb_band
from vervana.forecast.kill import load_band_decision
from vervana.forecast.series import price_series
from vervana.geo import haversine_km
from vervana.models.entities import Commodity, Market
from vervana.models.inventory import InventoryLot
from vervana.models.observations import PriceObservation
from vervana.repository.inventory import position_for

_MIN_HISTORY = 15  # need enough days to build a usable band


def _latest_executable_paise(session, commodity_id: int, market_id: int) -> int | None:
    from vervana.db.base import SourceClass

    obs = session.scalar(
        select(PriceObservation)
        .where(
            PriceObservation.commodity_id == commodity_id,
            PriceObservation.market_id == market_id,
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
        .limit(1)
    )
    return int(obs.canonical_price_paise_per_kg) if obs else None


def _outbound_paise(lot: InventoryLot, market: Market | None, rate_per_tonne_km: float):
    """Freight warehouse -> destination market, paise/kg, or None when distance is unknown
    (never a guessed zero). Mirrors the sourcing freight estimate (RISK[R15])."""
    if (
        market is None
        or lot.warehouse_lat is None
        or lot.warehouse_lon is None
        or market.latitude is None
        or market.longitude is None
    ):
        return None
    dist = haversine_km(
        (lot.warehouse_lat, lot.warehouse_lon),
        (float(market.latitude), float(market.longitude)),
    )
    return round(dist * rate_per_tonne_km / 10.0)  # ₹/tonne/km -> paise/kg


def _expected_price(session, commodity: str, series) -> ExpectedPrice:
    """Band p50 where the commodity's band cleared the kill bar; else anchor fallback
    (today's executable price held flat), which forces WAIT in the engine."""
    decision = load_band_decision(commodity)
    if decision.shippable and series.size >= _MIN_HISTORY:
        band = quantile_gb_band(series)
        return ExpectedPrice(
            paise_per_kg=round(band.p50),
            source="band-validated",
            shippable=True,
            reason=decision.reason or "band cleared the kill bar",
            band=band,
        )
    # Fallback: last price held flat. The baseline band is shown for context only.
    last = int(round(series[-1])) if series.size else 0
    band = conformal_band(series) if series.size >= _MIN_HISTORY else None
    return ExpectedPrice(
        paise_per_kg=last,
        source="anchor-fallback",
        shippable=False,
        reason=decision.reason or "band did not clear the kill bar; today's price held flat",
        band=band,
    )


@dataclass(frozen=True)
class LotDecisionContext:
    commodity: str
    market: str | None
    decision: BookDecision
    cost_rate_key: str
    note: str = ""


def decide_for_lot(session, lot: InventoryLot, *, horizon_days: int = 14) -> LotDecisionContext:
    settings = get_settings()
    commodity = session.get(Commodity, lot.commodity_id)
    cname = commodity.canonical_name if commodity else f"commodity#{lot.commodity_id}"
    market = session.get(Market, lot.intended_market_id) if lot.intended_market_id else None
    mname = market.canonical_name if market else None

    pos = position_for(session, lot.id)
    note = ""

    if market is None:
        return LotDecisionContext(
            commodity=cname,
            market=None,
            decision=BookDecision(
                verdict="WAIT",
                why="No destination market set on this lot — cannot compare hold vs sell.",
                uncertainties=["set an intended market to enable a decision"],
                invalidated_if=["an intended market and a current price become available"],
            ),
            cost_rate_key=load_cost_rates(cname).key,
            note="no intended market",
        )

    series = price_series(session, commodity_id=lot.commodity_id, market_id=market.id)
    immediate = _latest_executable_paise(session, lot.commodity_id, market.id)
    if immediate is None or series.size == 0:
        return LotDecisionContext(
            commodity=cname,
            market=mname,
            decision=BookDecision(
                verdict="WAIT",
                why=f"No executable price on record for {cname} @ {mname} — decision gated.",
                uncertainties=["no current price evidence"],
                invalidated_if=["a price is captured for this commodity-market"],
            ),
            cost_rate_key=load_cost_rates(cname).key,
            note="no price evidence",
        )

    expected = _expected_price(session, cname, series)
    rates = load_cost_rates(cname)
    outbound = _outbound_paise(lot, market, settings.freight_rate_per_tonne_km)
    hold = carrying_cost(
        rates=rates,
        purchase_price_paise_per_kg=lot.purchase_price_paise_per_kg,
        expected_sale_price_paise_per_kg=expected.paise_per_kg,
        days=horizon_days,
        outbound_paise_per_kg=outbound,
    )
    now = sell_now_cost(outbound)

    reroute = _reroute_candidate(session, lot, market, outbound, immediate, now)

    decision = decide(
        commodity=cname,
        expected=expected,
        immediate_price_paise_per_kg=immediate,
        hold_costs=hold,
        now_costs=now,
        horizon_days=horizon_days,
        flood=None,  # destination flood flag lands in M19 (see module docstring)
        reroute=reroute,
    )
    if pos is not None:
        note = f"{pos.remaining_kg:g} kg remaining of {float(lot.quantity_kg):g} kg"
    return LotDecisionContext(
        commodity=cname, market=mname, decision=decision, cost_rate_key=rates.key, note=note
    )


def _reroute_candidate(
    session, lot: InventoryLot, intended: Market, outbound_intended, net_now_intended_cost, _now
) -> RerouteAlt | None:
    """Best alternative destination by net executable price minus outbound freight, offered
    only where freight is estimable (warehouse + market coords). Returns None otherwise —
    never a reroute that ignores freight."""
    from vervana.db.base import SourceClass

    settings = get_settings()
    # Latest executable price per OTHER market for this commodity.
    rows = session.execute(
        select(PriceObservation, Market)
        .join(Market, Market.id == PriceObservation.market_id)
        .where(
            PriceObservation.commodity_id == lot.commodity_id,
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
            Market.id != intended.id,
        )
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    ).all()
    best: RerouteAlt | None = None
    seen: set[int] = set()
    for obs, mkt in rows:
        if mkt.id in seen:
            continue
        seen.add(mkt.id)
        outbound = _outbound_paise(lot, mkt, settings.freight_rate_per_tonne_km)
        if outbound is None:
            continue  # distance unknown -> never offered as a reroute
        net = int(obs.canonical_price_paise_per_kg) - outbound
        if best is None or net > best.net_paise_per_kg:
            best = RerouteAlt(
                market=mkt.canonical_name,
                net_paise_per_kg=net,
                reason=f"executable ₹{obs.canonical_price_paise_per_kg / 100:.2f}/kg "
                f"less freight {outbound}p",
            )
    return best
