"""Sourcing layer: landed-cost ranking + real buyer/supplier directory.

The benchmark answers "cheapest mandi at source". This adds the logistics step a
B2B buyer actually cares about: cheapest mandi *delivered to me*. For one
commodity it takes the latest wholesale rupees/kg per market (executed_summary
only - never blended with retail, the same guard as everywhere) and adds an
ESTIMATED freight cost = distance x rate, re-ranking by landed cost.

Honesty:
  * freight is an estimate - a flat rupees/tonne/km rate (RISK[R15]) over a
    state-centroid distance approximation. It is always shown AS an estimate with
    the rate visible, never a quoted freight price;
  * a market whose state has no known centroid gets distance/landed = None and is
    listed separately as "distance unknown", never guessed;
  * the mandi IS the supplier - real registry data. Contacts and buyers come only
    from `add_supplier_contact` / `add_buyer` (human-entered, provenance required).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.db.base import SourceClass
from vervana.geo import canonical_state, state_distance_km
from vervana.models.entities import Commodity, Market
from vervana.models.observations import PriceObservation
from vervana.models.sourcing import Buyer, Supplier, SupplierContact
from vervana.time import now_utc


def _latest_wholesale_by_market(session: Session, commodity: str) -> list[dict]:
    """Latest executed_summary rupees/kg per market for one commodity."""
    c = session.scalar(select(Commodity).where(Commodity.canonical_name == commodity))
    if c is None:
        return []
    seen: set[int] = set()
    out: list[dict] = []
    for obs, mname, mstate, mid in session.execute(
        select(PriceObservation, Market.canonical_name, Market.state, Market.id)
        .join(Market, Market.id == PriceObservation.market_id)
        .where(
            PriceObservation.commodity_id == c.id,
            PriceObservation.source_class == SourceClass.executed_summary,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    ):
        if mid in seen:
            continue
        seen.add(mid)
        out.append(
            {
                "market_id": mid,
                "market": mname,
                "state": mstate,
                "wholesale_paise": obs.canonical_price_paise_per_kg,
                "obs_id": obs.id,
            }
        )
    return out


def _contacts_by_market(session: Session, market_ids: list[int]) -> dict[int, int]:
    """Count of real supplier contacts per market (for the 'reachable' flag)."""
    if not market_ids:
        return {}
    counts: dict[int, int] = {}
    for (mid,) in session.execute(
        select(SupplierContact.market_id).where(SupplierContact.market_id.in_(market_ids))
    ):
        counts[mid] = counts.get(mid, 0) + 1
    return counts


def landed_cost_ranking(
    session: Session,
    commodity: str,
    buyer_state: str | None,
    rate_per_tonne_km: float,
) -> dict:
    """Rank sourcing mandis by estimated landed cost (wholesale + freight)."""
    base = _latest_wholesale_by_market(session, commodity)
    contacts = _contacts_by_market(session, [r["market_id"] for r in base])
    known: list[dict] = []
    unknown: list[dict] = []
    buyer_known = canonical_state(buyer_state) is not None
    for r in base:
        dist = state_distance_km(buyer_state, r["state"]) if buyer_known else None
        row = {
            **r,
            "wholesale_rupees": r["wholesale_paise"] / 100,
            "contacts": contacts.get(r["market_id"], 0),
            "distance_km": dist,
        }
        if dist is None:
            row["freight_rupees"] = None
            row["landed_paise"] = None
            row["landed_rupees"] = None
            unknown.append(row)
        else:
            freight_paise = round(dist * rate_per_tonne_km / 10.0)  # rupees/tonne/km -> paise/kg
            row["freight_rupees"] = freight_paise / 100
            row["landed_paise"] = r["wholesale_paise"] + freight_paise
            row["landed_rupees"] = row["landed_paise"] / 100
            known.append(row)
    known.sort(key=lambda x: x["landed_paise"])
    unknown.sort(key=lambda x: x["wholesale_paise"])
    rows = known + unknown

    cheapest_source = min(base, key=lambda x: x["wholesale_paise"]) if base else None
    cheapest_delivered = known[0] if known else None
    # The headline insight: does adding freight change who is cheapest?
    reordered = bool(
        cheapest_source
        and cheapest_delivered
        and cheapest_source["market_id"] != cheapest_delivered["market_id"]
    )
    return {
        "rows": rows,
        "n_markets": len(base),
        "cheapest_source": cheapest_source,
        "cheapest_delivered": cheapest_delivered,
        "reordered": reordered,
        "rate": rate_per_tonne_km,
        "buyer_state": buyer_state if buyer_known else None,
        "buyer_state_known": buyer_known,
    }


def sourced_commodities(session: Session) -> list[str]:
    """Commodities that have any wholesale reference (selectable for sourcing)."""
    return [
        c
        for (c,) in session.execute(
            select(Commodity.canonical_name)
            .join(PriceObservation, PriceObservation.commodity_id == Commodity.id)
            .where(PriceObservation.source_class == SourceClass.executed_summary)
            .distinct()
            .order_by(Commodity.canonical_name)
        )
    ]


# --- directory: real contacts & buyers (human-entered, provenance required) ---


def add_supplier_contact(session: Session, *, market_id: int, contact_name: str, **kw) -> int:
    row = SupplierContact(
        market_id=market_id,
        contact_name=contact_name,
        role=kw.get("role", ""),
        phone=kw.get("phone") or None,
        email=kw.get("email") or None,
        note=kw.get("note") or None,
        source=kw.get("source") or "manual entry",
        added_at=now_utc(),
    )
    session.add(row)
    session.flush()
    return row.id


def supplier_contacts(session: Session, market_id: int) -> list[SupplierContact]:
    return list(
        session.scalars(
            select(SupplierContact)
            .where(SupplierContact.market_id == market_id)
            .order_by(SupplierContact.id)
        )
    )


def add_buyer(session: Session, *, name: str, **kw) -> int:
    row = Buyer(
        name=name,
        kind=kw.get("kind", ""),
        city=kw.get("city") or None,
        state=kw.get("state") or None,
        commodities=(kw.get("commodities") or "").strip(),
        phone=kw.get("phone") or None,
        email=kw.get("email") or None,
        note=kw.get("note") or None,
        source=kw.get("source") or "manual entry",
        added_at=now_utc(),
    )
    session.add(row)
    session.flush()
    return row.id


def import_suppliers(session: Session, records: list[dict]) -> dict:
    """Upsert supplier organisations (idempotent on commodity+name+state)."""
    existing = {(s.commodity, s.name, s.state): s for s in session.scalars(select(Supplier))}
    added = updated = 0
    for r in records:
        if not r.get("name") or not r.get("source_url"):
            continue  # provenance + identity required
        key = (r["commodity"], r["name"], r.get("state"))
        found = existing.get(key)
        if found is None:
            session.add(
                Supplier(
                    commodity=r["commodity"],
                    name=r["name"],
                    org_type=r.get("org_type", ""),
                    state=r.get("state"),
                    district=r.get("district"),
                    address=r.get("address"),
                    contact_name=r.get("contact_name"),
                    phone=r.get("phone"),
                    email=r.get("email"),
                    source=r["source"],
                    source_url=r["source_url"],
                    added_at=now_utc(),
                )
            )
            added += 1
        else:
            # Refresh contact fields if the directory changed.
            for f in ("phone", "email", "contact_name", "address"):
                if r.get(f) and getattr(found, f) != r[f]:
                    setattr(found, f, r[f])
                    updated += 1
    session.flush()
    return {"added": added, "updated": updated, "total": len(records)}


def list_suppliers(session: Session, commodity: str, state: str = "") -> list[dict]:
    stmt = (
        select(Supplier)
        .where(Supplier.commodity == commodity)
        .order_by(Supplier.state, Supplier.name)
    )
    if state:
        stmt = stmt.where(Supplier.state == state)
    out = []
    for s in session.scalars(stmt):
        out.append(
            {
                "name": s.name,
                "org_type": s.org_type,
                "state": s.state,
                "address": s.address,
                "contact_name": s.contact_name,
                "phone": s.phone,
                "email": s.email,
                "source": s.source,
                "source_url": s.source_url,
            }
        )
    return out


def supplier_states(session: Session, commodity: str) -> list[str]:
    return [
        s
        for (s,) in session.execute(
            select(Supplier.state)
            .where(Supplier.commodity == commodity, Supplier.state.is_not(None))
            .distinct()
            .order_by(Supplier.state)
        )
    ]


def list_buyers(session: Session) -> list[dict]:
    out = []
    for b in session.scalars(select(Buyer).order_by(Buyer.name)):
        out.append(
            {
                "id": b.id,
                "name": b.name,
                "kind": b.kind,
                "city": b.city,
                "state": b.state,
                "commodities": [c.strip() for c in (b.commodities or "").split(",") if c.strip()],
                "phone": b.phone,
                "email": b.email,
                "source": b.source,
            }
        )
    return out
