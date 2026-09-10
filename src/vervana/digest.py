"""HoReCa procurement digest (M3 — the pending WhatsApp piece).

Persona decision (2026-09-10): the first customer is HoReCa buyers + quick-commerce
operators, NOT mandi traders. This resolves the R2 fork in favour of the research brief.

The digest's value to a HoReCa buyer is the **spread**: today's wholesale (mandi) price
vs today's quick-commerce retail price for the same commodity — how much they save by
procuring wholesale. The two are shown SIDE BY SIDE and never blended (the source-class
guard forbids averaging them); the spread is a labelled difference, not an average.

Every number carries provenance (an evidence id), its source class, and a confidence —
including here (Part 7). Output is plain text suitable for a WhatsApp message.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.confidence import price_confidence
from vervana.db.base import SourceClass
from vervana.models.entities import Commodity
from vervana.models.observations import PriceObservation
from vervana.time import now_utc, to_ist

# RISK[R2-BEACHHEAD]: This digest is deliberately shaped for HoReCa buyers, not mandi
# traders. The blueprint's original beachhead was traders, but the research ranks them
# LAST on willingness to pay and HoReCa FIRST; traders stand in the shed and generate the
# price, so they will not pay us for it. Building trader-shaped output would be building
# for the wrong customer. If a future feature targets the trader persona, re-open this.
# Evidence: docs/RISK_REGISTER.md#r2-beachhead; OPEN_QUESTIONS #4 (resolved)
# Verdict: RESOLVED — persona set to HoReCa + quick-commerce (2026-09-10, founder).

DEFAULT_BASKET = ["Potato", "Onion", "Tomato", "Capsicum", "Cauliflower", "Green Chilli"]


@dataclass
class Line:
    commodity: str
    wholesale_kg: int | None
    wholesale_obs: int | None
    wholesale_conf: float | None
    retail_kg: int | None
    retail_obs: int | None
    retail_conf: float | None
    retail_platform: str | None

    @property
    def spread_kg(self) -> int | None:
        if self.wholesale_kg is None or self.retail_kg is None:
            return None
        return self.retail_kg - self.wholesale_kg


def _latest(session: Session, commodity_id: int, source_class: SourceClass):
    return session.scalar(
        select(PriceObservation)
        .where(
            PriceObservation.commodity_id == commodity_id,
            PriceObservation.source_class == source_class,
            PriceObservation.canonical_price_paise_per_kg.is_not(None),
        )
        .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
    )


def build_lines(session: Session, commodities: list[str] | None = None) -> list[Line]:
    names = commodities or DEFAULT_BASKET
    lines: list[Line] = []
    for name in names:
        c = session.scalar(select(Commodity).where(Commodity.canonical_name == name))
        if c is None:
            continue
        wh = _latest(session, c.id, SourceClass.executed_summary)
        rt = _latest(session, c.id, SourceClass.retail_offer)
        platform = None
        if rt is not None:
            from vervana.models.retail import RetailOfferDetail

            d = session.scalar(
                select(RetailOfferDetail).where(RetailOfferDetail.observation_id == rt.id)
            )
            platform = d.platform if d else None
        lines.append(
            Line(
                commodity=name,
                wholesale_kg=wh.canonical_price_paise_per_kg if wh else None,
                wholesale_obs=wh.id if wh else None,
                wholesale_conf=price_confidence(wh) if wh else None,
                retail_kg=rt.canonical_price_paise_per_kg if rt else None,
                retail_obs=rt.id if rt else None,
                retail_conf=price_confidence(rt) if rt else None,
                retail_platform=platform,
            )
        )
    return lines


def _rupees(paise: int | None) -> str:
    return "—" if paise is None else f"₹{paise / 100:,.0f}/kg"


def build_digest(session: Session, commodities: list[str] | None = None) -> str:
    # RISK[R1-INFO-CHANGES-BEHAVIOUR]: This digest assumes that showing a buyer the
    # wholesale-vs-retail spread will change their procurement decisions. A 72-village RCT
    # (Mitra, Mookherjee, Torero & Visaria 2017) found daily price info did NOT move
    # farmer outcomes. That was farmers selling; our buyer is a HoReCa procurement buyer,
    # a different (plausibly more elastic) decision — but the info→action link is still an
    # ASSUMPTION, not a proven fact. Validate with actual buyer behaviour before pricing on
    # it. Evidence: docs/RISK_REGISTER.md#r1-info-changes-behaviour
    # Verdict: PENDING
    lines = build_lines(session, commodities)
    today = to_ist(now_utc()).strftime("%d %b %Y")
    out = [f"*Vervana — HoReCa procurement digest*  ({today})", ""]
    any_data = False
    for ln in lines:
        if ln.wholesale_kg is None and ln.retail_kg is None:
            out.append(f"• {ln.commodity}: no price today")
            continue
        any_data = True
        wh = (
            f"wholesale {_rupees(ln.wholesale_kg)}"
            if ln.wholesale_kg is not None
            else "wholesale —"
        )
        rt = (
            f"retail {_rupees(ln.retail_kg)}"
            + (f" ({ln.retail_platform})" if ln.retail_platform else "")
            if ln.retail_kg is not None
            else "retail —"
        )
        spread = ""
        if ln.spread_kg is not None and ln.wholesale_kg:
            pct = ln.spread_kg / ln.wholesale_kg * 100
            amt = f"₹{abs(ln.spread_kg) / 100:,.0f}/kg"
            if ln.spread_kg > 0:
                spread = f"  → retail {amt} above wholesale (+{pct:.0f}%)"
            elif ln.spread_kg < 0:
                spread = f"  → retail {amt} below wholesale ({pct:.0f}%)"
        out.append(f"• *{ln.commodity}*: {wh} | {rt}{spread}")
        ev = []
        if ln.wholesale_obs:
            ev.append(
                f"wholesale ev#{ln.wholesale_obs} · executed_summary · conf {ln.wholesale_conf}"
            )
        if ln.retail_obs:
            ev.append(f"retail ev#{ln.retail_obs} · retail_offer · conf {ln.retail_conf}")
        out.append("    " + " ; ".join(ev))
    if not any_data:
        out.append("_No priced commodities in the basket yet._")
    out += [
        "",
        "_Wholesale = latest available Agmarknet price (currently national, not Delhi — "
        "Delhi mandi data is absent from the feed, so spreads are indicative until it "
        "arrives). Wholesale and retail are shown separately and never averaged._",
        "_Not trading advice. Wholesale via Agmarknet (data.gov.in); DMI does not warrant "
        "accuracy. Retail via manual quick-commerce panel._",
    ]
    return "\n".join(out)
