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
    wholesale_kg: int | None  # national Agmarknet (executed_summary)
    wholesale_obs: int | None
    wholesale_conf: float | None
    retail_kg: int | None
    retail_obs: int | None
    retail_conf: float | None
    retail_platform: str | None
    delhi_video_kg: int | None = None  # Delhi video quote (quote_indicative, units-applied, R3)
    delhi_video_obs: int | None = None
    delhi_video_conf: float | None = None

    @property
    def ref_kg(self) -> int | None:
        """The wholesale reference for the spread: Delhi video preferred (it's Delhi-
        specific), else national Agmarknet."""
        return self.delhi_video_kg if self.delhi_video_kg is not None else self.wholesale_kg

    @property
    def ref_label(self) -> str:
        return "Delhi video" if self.delhi_video_kg is not None else "national Agmarknet"

    @property
    def spread_kg(self) -> int | None:
        if self.ref_kg is None or self.retail_kg is None:
            return None
        return self.retail_kg - self.ref_kg


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


def _national_wholesale(session: Session, commodity_id: int):
    """A representative national wholesale ₹/kg: the MEDIAN of recent Agmarknet rows across
    all markets (a single 'latest' row can be an arbitrary cheap/dear market). Returns
    (median_kg_paise, representative_evidence_id) or None."""
    import statistics

    rows = list(
        session.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.commodity_id == commodity_id,
                PriceObservation.source_class == SourceClass.executed_summary,
                PriceObservation.canonical_price_paise_per_kg.is_not(None),
            )
            .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
            .limit(400)
        )
    )
    if not rows:
        return None
    median_kg = round(statistics.median(o.canonical_price_paise_per_kg for o in rows))
    rep = min(rows, key=lambda o: abs(o.canonical_price_paise_per_kg - median_kg))
    return median_kg, rep.id


# A fresh-produce ₹/kg outside this band means the unit inference is unreliable for this
# commodity (e.g. a per-crate quote forced through the wrong scale) — suppress it.
_PLAUSIBLE_KG_PAISE = (300, 50_000)  # ₹3 .. ₹500 per kg


def _latest_delhi_video(session: Session, commodity_id: int, scale: float | None):
    """A robust recent Delhi video price: the MEDIAN of the most recent quotes (not a single
    possibly-outlier latest one), scaled to ₹/kg, and only if the result is plausible."""
    import statistics

    from vervana.analytics.groundtruth import VIDEO_MARKETS
    from vervana.models.entities import Market

    if not scale:
        return None
    market_ids = [
        m.id
        for m in session.scalars(select(Market).where(Market.canonical_name.in_(VIDEO_MARKETS)))
    ]
    if not market_ids:
        return None
    recent = list(
        session.scalars(
            select(PriceObservation)
            .where(
                PriceObservation.commodity_id == commodity_id,
                PriceObservation.source_class == SourceClass.quote_indicative,
                PriceObservation.market_id.in_(market_ids),
            )
            .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
            .limit(15)
        )
    )
    if not recent:
        return None
    kg = round(
        statistics.median((o.price_low_paise + o.price_high_paise) / 2 * scale for o in recent)
    )
    if not (_PLAUSIBLE_KG_PAISE[0] <= kg <= _PLAUSIBLE_KG_PAISE[1]):
        return None  # implausible ⇒ unit inference unreliable here; fall back to national
    return recent[0].id, kg


def commodity_options(session: Session) -> dict:
    """Commodities selectable for the digest, split by evidence available.

    'qcomm' commodities have a quick-commerce retail offer AND a wholesale
    reference, so they yield a full spread. 'wholesale_only' commodities have an
    Agmarknet reference but no retail panel price yet - selectable, but the board
    shows their wholesale price with no spread (honest, not a fabricated retail).
    """

    def _names(source_class: SourceClass) -> set[str]:
        return set(
            session.scalars(
                select(Commodity.canonical_name)
                .join(PriceObservation, PriceObservation.commodity_id == Commodity.id)
                .where(
                    PriceObservation.source_class == source_class,
                    PriceObservation.canonical_price_paise_per_kg.is_not(None),
                )
                .distinct()
            )
        )

    wholesale = _names(SourceClass.executed_summary)
    retail = _names(SourceClass.retail_offer)
    qcomm = sorted(retail & wholesale)
    wholesale_only = sorted(wholesale - retail)
    return {"qcomm": qcomm, "wholesale_only": wholesale_only}


def build_lines(session: Session, commodities: list[str] | None = None) -> list[Line]:
    from vervana.analytics.unit_inference import infer_units

    names = commodities or DEFAULT_BASKET
    units = infer_units(session)
    lines: list[Line] = []
    for name in names:
        c = session.scalar(select(Commodity).where(Commodity.canonical_name == name))
        if c is None:
            continue
        nat = _national_wholesale(session, c.id)
        rt = _latest(session, c.id, SourceClass.retail_offer)
        platform = None
        if rt is not None:
            from vervana.models.retail import RetailOfferDetail

            d = session.scalar(
                select(RetailOfferDetail).where(RetailOfferDetail.observation_id == rt.id)
            )
            platform = d.platform if d else None
        u = units.get(name)
        video = _latest_delhi_video(session, c.id, u.scale_to_kg if u else None)
        lines.append(
            Line(
                commodity=name,
                wholesale_kg=nat[0] if nat else None,
                wholesale_obs=nat[1] if nat else None,
                wholesale_conf=0.8 if nat else None,
                retail_kg=rt.canonical_price_paise_per_kg if rt else None,
                retail_obs=rt.id if rt else None,
                retail_conf=price_confidence(rt) if rt else None,
                retail_platform=platform,
                delhi_video_kg=video[1] if video else None,
                delhi_video_obs=video[0] if video else None,
                delhi_video_conf=0.5 if video else None,  # quote_indicative reliability (§5.4)
            )
        )
    return lines


def _rupees(paise: int | None) -> str:
    return "—" if paise is None else f"₹{paise / 100:,.0f}/kg"


def build_digest(
    session: Session,
    commodities: list[str] | None = None,
    *,
    lines: list[Line] | None = None,
) -> str:
    # RISK[R1-INFO-CHANGES-BEHAVIOUR]: This digest assumes that showing a buyer the
    # wholesale-vs-retail spread will change their procurement decisions. A 72-village RCT
    # (Mitra, Mookherjee, Torero & Visaria 2017) found daily price info did NOT move
    # farmer outcomes. That was farmers selling; our buyer is a HoReCa procurement buyer,
    # a different (plausibly more elastic) decision — but the info→action link is still an
    # ASSUMPTION, not a proven fact. Validate with actual buyer behaviour before pricing on
    # it. Evidence: docs/RISK_REGISTER.md#r1-info-changes-behaviour
    # Verdict: PENDING
    if lines is None:
        lines = build_lines(session, commodities)
    today = to_ist(now_utc()).strftime("%d %b %Y")
    out = [f"*Vervana — HoReCa procurement digest*  ({today})", ""]
    any_data = False
    for ln in lines:
        if ln.ref_kg is None and ln.retail_kg is None:
            out.append(f"• {ln.commodity}: no price today")
            continue
        any_data = True
        parts = []
        if ln.delhi_video_kg is not None:
            parts.append(f"Delhi(video) {_rupees(ln.delhi_video_kg)}")
        if ln.wholesale_kg is not None:
            parts.append(f"national {_rupees(ln.wholesale_kg)}")
        rt = (
            f"retail {_rupees(ln.retail_kg)}"
            + (f" ({ln.retail_platform})" if ln.retail_platform else "")
            if ln.retail_kg is not None
            else "retail —"
        )
        parts.append(rt)
        spread = ""
        if ln.spread_kg is not None and ln.ref_kg:
            pct = ln.spread_kg / ln.ref_kg * 100
            amt = f"₹{abs(ln.spread_kg) / 100:,.0f}/kg"
            direction = "above" if ln.spread_kg > 0 else "below"
            sign = "+" if ln.spread_kg > 0 else ""
            spread = f"  → retail {amt} {direction} {ln.ref_label} ({sign}{pct:.0f}%)"
        out.append(f"• *{ln.commodity}*: {' | '.join(parts)}{spread}")
        ev = []
        if ln.delhi_video_obs:
            ev.append(
                f"Delhi-video ev#{ln.delhi_video_obs} · quote_indicative · "
                f"conf {ln.delhi_video_conf}"
            )
        if ln.wholesale_obs:
            ev.append(
                f"national ev#{ln.wholesale_obs} · executed_summary · conf {ln.wholesale_conf}"
            )
        if ln.retail_obs:
            ev.append(f"retail ev#{ln.retail_obs} · retail_offer · conf {ln.retail_conf}")
        out.append("    " + " ; ".join(ev))
    if not any_data:
        out.append("_No priced commodities in the basket yet._")
    out += [
        "",
        "_Spread reference = Delhi video quote where available (unit-inferred to ₹/kg; an "
        "UNVERIFIED quote signal, not an executed price — R3), else national Agmarknet. "
        "All sources shown separately and never averaged._",
        "_Not trading advice. National wholesale via Agmarknet (data.gov.in); DMI does not "
        "warrant accuracy. Delhi via manually-transcribed video quotes. Retail via manual "
        "quick-commerce panel._",
    ]
    return "\n".join(out)
