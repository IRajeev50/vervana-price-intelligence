"""DB-side composition for The Book (M17): turn a stored lot into a decision.

This is the only Book layer that touches the store. It fetches the executable price, the
band (validated or baseline), outbound freight, and reroute candidates, then hands plain
values to the pure `decision.decide`. Kept thin so the honest logic stays in the tested
pure core.

Destination flood flag (M19a): a lot's intended market is mapped to a riverine destination
zone (`destination_zones.csv`); the latest recorded/fetched overlay for that zone becomes a
`FloodFlag` passed to the engine, and a reroute into another flood-exposed zone is marked
not flood-safe. Riverine-only, never a price feature; absence of an overlay reads as "access
pending — NOT no risk", never as safe. The live gauge pull (M19b) stays access-gated.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from vervana.book.costs import carrying_cost, load_cost_rates, sell_now_cost
from vervana.book.decision import BookDecision, ExpectedPrice, FloodFlag, RerouteAlt, decide
from vervana.config import get_settings
from vervana.db.base import SourceClass
from vervana.forecast.band import conformal_band, quantile_gb_band
from vervana.forecast.kill import load_band_decision
from vervana.forecast.series import price_series
from vervana.geo import haversine_km
from vervana.models.entities import Commodity, Market
from vervana.models.inventory import InventoryLot
from vervana.models.observations import PriceObservation
from vervana.repository.flood_overlay import latest_overlay_for_zone
from vervana.repository.inventory import position_for
from vervana.repository.prices import arrivals_series
from vervana.supply.destination_zones import zone_for_market
from vervana.supply.floodhub import severity_is_risk

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


def _destination_flood(session, market_name: str | None) -> tuple[FloodFlag | None, str]:
    """Resolve a market's riverine destination-flood flag and a human line for the UI.

    Returns (flag, line). The flag is None (no action) unless a mapped zone has an overlay;
    the line is always honest about which case we are in — crucially, a mapped zone with no
    overlay says "access pending", NEVER "no flood risk".
    """
    zone = zone_for_market(market_name or "")
    if zone is None:
        return None, "flood overlay (riverine): destination not in a mapped flood zone."
    row = latest_overlay_for_zone(session, zone.zone)
    if row is None:
        return None, (
            f"flood overlay (riverine) {zone.zone}: Flood Hub access pending — no overlay "
            f"(this is NOT 'no flood risk', just no data)."
        )
    is_risk = severity_is_risk(row.severity)
    issued = row.issued_time.date().isoformat() if row.issued_time else "undated"
    flag = FloodFlag(zone=zone.zone, severity=row.severity, is_risk=is_risk)
    trend = f", {row.trend.lower()}" if row.trend else ""
    line = (
        f"flood overlay (riverine) {zone.zone}: {row.severity}{trend} "
        f"(issued {issued}; {row.source})."
    )
    return flag, line


def _market_is_flood_exposed(session, market_name: str) -> bool:
    """True only when the market maps to a destination zone that currently carries an
    above-normal riverine overlay — so a reroute never moves into another flooded hub."""
    flag, _ = _destination_flood(session, market_name)
    return flag is not None and flag.is_risk


@dataclass(frozen=True)
class LotDecisionContext:
    commodity: str
    market: str | None
    decision: BookDecision
    cost_rate_key: str
    note: str = ""
    flood_line: str = ""


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

    flood, flood_line = _destination_flood(session, mname)

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
            flood_line=flood_line,
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
        flood=flood,  # M19a: destination riverine overlay, or None (no zone / access pending)
        reroute=reroute,
    )
    if pos is not None:
        note = f"{pos.remaining_kg:g} kg remaining of {float(lot.quantity_kg):g} kg"
    return LotDecisionContext(
        commodity=cname,
        market=mname,
        decision=decision,
        cost_rate_key=rates.key,
        note=note,
        flood_line=flood_line,
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
                # Never reroute into another flood-exposed destination hub (M19a).
                flood_safe=not _market_is_flood_exposed(session, mkt.canonical_name),
            )
    return best


# --- commodity study (M-study): analyse ANY commodity without a stored lot ------------
#
# The lot view answers "what should I do with THIS stock?"; the study answers "what is the
# picture for this commodity?" It runs the same honest engine on the commodity's best-covered
# market, holding 1 kg bought at today's price, so the kill gate, carrying economics and price
# landscape all show — no lot required. There is no origin warehouse in a study, so outbound
# freight and reroute are deliberately omitted (they need a real origin), never guessed.


@dataclass(frozen=True)
class CommodityStudy:
    commodity: str
    market: str | None  # the best-covered market the study is anchored on
    n_days: int  # executed-day history at that market
    decision: BookDecision
    cost_rate_key: str
    # Price landscape across every reporting market (latest executed price each), in paise/kg.
    n_markets: int = 0
    price_lo_paise: int | None = None
    price_mid_paise: int | None = None
    price_hi_paise: int | None = None
    flood_line: str = ""
    arrivals_note: str = ""

    @property
    def spread_paise(self) -> int | None:
        """High minus low of the latest-per-market prices — the cross-market dispersion.
        None when the commodity has no price landscape yet (never a guessed zero)."""
        if self.price_lo_paise is None or self.price_hi_paise is None:
            return None
        return self.price_hi_paise - self.price_lo_paise


def rank_by_spread(studies: list[CommodityStudy]) -> list[CommodityStudy]:
    """Order studies by cross-market price spread, widest first; studies with no landscape
    (no spread) sort last. A wide spread flags where the same commodity trades far apart
    across mandis — the dispersion worth a closer look. Not a HOLD/RELEASE signal."""
    return sorted(
        studies,
        key=lambda s: (s.spread_paise is None, -(s.spread_paise or 0)),
    )


def study_commodities(session) -> list[str]:
    """Every commodity with executed-summary price data, sorted — the study picker list."""
    rows = session.execute(
        select(Commodity.canonical_name)
        .join(PriceObservation, PriceObservation.commodity_id == Commodity.id)
        .where(
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
        .distinct()
        .order_by(Commodity.canonical_name)
    ).all()
    return [r[0] for r in rows]


def _representative_market(session, commodity_id: int):
    """The market with the most executed-day history for a commodity (best series to study)."""
    day = func.date(PriceObservation.observed_at)
    row = session.execute(
        select(
            PriceObservation.market_id,
            func.count(func.distinct(day)).label("d"),
        )
        .where(
            PriceObservation.commodity_id == commodity_id,
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
        .group_by(PriceObservation.market_id)
        .order_by(func.count(func.distinct(day)).desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None, 0
    market = session.get(Market, row[0])
    return row[0], market, int(row[1])


def _price_landscape(session, commodity_id: int) -> tuple[int, int | None, int | None, int | None]:
    """(n_markets, lo, mid, hi) paise from the latest executed price in each reporting market."""
    rows = session.execute(
        select(PriceObservation.market_id, PriceObservation.canonical_price_paise_per_kg)
        .where(
            PriceObservation.commodity_id == commodity_id,
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    ).all()
    latest: dict[int, int] = {}
    for mid, p in rows:
        if mid not in latest:
            latest[mid] = int(p)
    if not latest:
        return 0, None, None, None
    vals = sorted(latest.values())
    mid_val = vals[len(vals) // 2]
    return len(vals), vals[0], mid_val, vals[-1]


def study_commodity(session, commodity: str, *, horizon_days: int = 14) -> CommodityStudy:
    """Advisory study of a commodity with no stored lot. Same honesty gate as the lot view."""
    crow = session.scalar(select(Commodity).where(Commodity.canonical_name == commodity))
    rates = load_cost_rates(commodity)
    if crow is None:
        return CommodityStudy(
            commodity=commodity,
            market=None,
            n_days=0,
            decision=BookDecision(
                verdict="WAIT",
                why=f"'{commodity}' is not a known commodity in the registry.",
                uncertainties=["no such commodity"],
                invalidated_if=["the commodity is seeded and prices are captured"],
            ),
            cost_rate_key=rates.key,
        )

    mid, market, n_days = _representative_market(session, crow.id)
    n_markets, lo, mid_p, hi = _price_landscape(session, crow.id)
    if market is None:
        return CommodityStudy(
            commodity=commodity,
            market=None,
            n_days=0,
            decision=BookDecision(
                verdict="WAIT",
                why=f"No executable price on record for {commodity} — nothing to study yet.",
                uncertainties=["no current price evidence"],
                invalidated_if=["a price is captured for this commodity"],
            ),
            cost_rate_key=rates.key,
            n_markets=n_markets,
        )

    flood, flood_line = _destination_flood(session, market.canonical_name)
    series = price_series(session, commodity_id=crow.id, market_id=mid)
    immediate = _latest_executable_paise(session, crow.id, mid)
    expected = _expected_price(session, commodity, series)
    # A study has no origin warehouse, so outbound freight is unknown (never a guessed zero):
    # the carrying cost is storage + financing (on today's price as value basis) + spoilage.
    hold = carrying_cost(
        rates=rates,
        purchase_price_paise_per_kg=immediate or 0,
        expected_sale_price_paise_per_kg=expected.paise_per_kg,
        days=horizon_days,
        outbound_paise_per_kg=None,
    )
    now = sell_now_cost(None)
    decision = decide(
        commodity=commodity,
        expected=expected,
        immediate_price_paise_per_kg=immediate or 0,
        hold_costs=hold,
        now_costs=now,
        horizon_days=horizon_days,
        flood=flood,
        reroute=None,  # a study has no origin, so no freight-based reroute (never guessed)
    )

    arr = arrivals_series(session, commodity_id=crow.id, market_id=mid)
    arrivals_note = (
        f"latest captured arrivals {arr[-1][1]:g} t at {market.canonical_name} ({arr[-1][0]})"
        if arr
        else "no arrivals captured yet (stored going forward)"
    )
    return CommodityStudy(
        commodity=commodity,
        market=market.canonical_name,
        n_days=n_days,
        decision=decision,
        cost_rate_key=rates.key,
        n_markets=n_markets,
        price_lo_paise=lo,
        price_mid_paise=mid_p,
        price_hi_paise=hi,
        flood_line=flood_line,
        arrivals_note=arrivals_note,
    )
