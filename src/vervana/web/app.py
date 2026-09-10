"""Vervana serving layer (M3): a browsable, provenance-first web app + JSON API.

Every displayed price links to its evidence (source_url + raw_quote) and shows its
source class and a confidence factor. The DMI accuracy disclaimer and GODL-India
attribution appear on every page (Part 7).
"""

from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from vervana.analytics.coverage import compute_coverage, r5_verdict
from vervana.db.base import SourceClass
from vervana.db.engine import session_scope
from vervana.models.entities import Alias, Commodity, Market
from vervana.models.ingest import IngestRun
from vervana.models.observations import PriceObservation
from vervana.models.review import AliasReview
from vervana.repository.review import approve, pending
from vervana.time import format_ist, now_utc, to_ist

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Base reliability by source class — one factor of the confidence score (§5.4).
# Cross-source agreement is not computed yet (needs multiple comparable sources), so we
# show this honestly as a partial confidence, not a finished composite.
SOURCE_RELIABILITY = {
    SourceClass.executed_trade: 0.95,
    SourceClass.executed_summary: 0.80,
    SourceClass.retail_offer: 0.70,
    SourceClass.quote_indicative: 0.50,
}

app = FastAPI(title="Vervana — Price Intelligence")


def _paise_to_rupee(paise: int | None) -> str:
    return "—" if paise is None else f"₹{paise / 100:,.2f}"


def _confidence(obs: PriceObservation) -> float:
    base = SOURCE_RELIABILITY.get(obs.source_class, 0.5)
    conv = float(obs.unit_conversion_confidence) if obs.unit_conversion_confidence else 1.0
    return round(base * conv, 2)


def _ctx(request: Request, **kw) -> dict:
    kw["request"] = request
    return kw


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with session_scope() as s:
        stats = {
            "observations": s.scalar(select(func.count()).select_from(PriceObservation)) or 0,
            "commodities": s.scalar(select(func.count()).select_from(Commodity)) or 0,
            "markets": s.scalar(select(func.count()).select_from(Market)) or 0,
            "aliases": s.scalar(select(func.count()).select_from(Alias)) or 0,
            "pending_reviews": s.scalar(
                select(func.count()).select_from(AliasReview).where(AliasReview.status == "pending")
            )
            or 0,
        }
        last_run = s.scalar(select(IngestRun).order_by(IngestRun.started_at.desc()))
        last = None
        if last_run:
            last = {
                "when": format_ist(last_run.started_at),
                "status": last_run.status,
                "accepted": last_run.accepted,
                "rows_in": last_run.rows_in,
            }
    probe = _read_probe()
    delhi_today = probe[-1]["delhi_rows"] if probe else "—"
    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        _ctx(request, stats=stats, last=last, delhi_today=delhi_today, probe_rows=len(probe)),
    )


@app.get("/prices", response_class=HTMLResponse)
def prices(
    request: Request,
    commodity: str = "",
    market: str = "",
    source_class: str = "",
    q: str = "",
    limit: int = 100,
):
    with session_scope() as s:
        stmt = (
            select(PriceObservation, Commodity.canonical_name, Market.canonical_name)
            .join(Commodity, Commodity.id == PriceObservation.commodity_id)
            .join(Market, Market.id == PriceObservation.market_id)
            .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
        )
        if commodity:
            stmt = stmt.where(Commodity.canonical_name == commodity)
        if market:
            stmt = stmt.where(Market.canonical_name == market)
        if source_class:
            stmt = stmt.where(PriceObservation.source_class == source_class)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(Commodity.canonical_name.ilike(like))
        rows = []
        for obs, cname, mname in s.execute(stmt.limit(limit)):
            rows.append(
                {
                    "id": obs.id,
                    "commodity": cname,
                    "market": mname,
                    "source_class": obs.source_class.value,
                    "low": _paise_to_rupee(obs.price_low_paise),
                    "high": _paise_to_rupee(obs.price_high_paise),
                    "canonical": _paise_to_rupee(obs.canonical_price_paise_per_kg),
                    "unit": obs.unit_raw,
                    "confidence": _confidence(obs),
                    "when": to_ist(obs.observed_at).strftime("%Y-%m-%d"),
                }
            )
        commodities = [
            c
            for (c,) in s.execute(
                select(Commodity.canonical_name).order_by(Commodity.canonical_name)
            )
        ]
        classes = [sc.value for sc in SourceClass]
    return TEMPLATES.TemplateResponse(
        request,
        "prices.html",
        _ctx(
            request,
            rows=rows,
            commodities=commodities,
            classes=classes,
            f_commodity=commodity,
            f_market=market,
            f_source_class=source_class,
            q=q,
        ),
    )


@app.get("/evidence/{obs_id}", response_class=HTMLResponse)
def evidence(request: Request, obs_id: int):
    with session_scope() as s:
        obs = s.get(PriceObservation, obs_id)
        if obs is None:
            return HTMLResponse("<h1>404 — no such observation</h1>", status_code=404)
        commodity = s.get(Commodity, obs.commodity_id)
        market = s.get(Market, obs.market_id)
        data = {
            "id": obs.id,
            "commodity": commodity.canonical_name if commodity else "?",
            "market": market.canonical_name if market else "?",
            "source_class": obs.source_class.value,
            "time_basis": obs.time_basis.value,
            "low": _paise_to_rupee(obs.price_low_paise),
            "high": _paise_to_rupee(obs.price_high_paise),
            "point": _paise_to_rupee(obs.price_point_paise),
            "canonical": _paise_to_rupee(obs.canonical_price_paise_per_kg),
            "unit_raw": obs.unit_raw,
            "kg_equivalent": obs.unit_kg_equivalent,
            "conversion_confidence": obs.unit_conversion_confidence,
            "confidence": _confidence(obs),
            "source_url": obs.source_url,
            "raw_quote": obs.raw_quote,
            "observed_at": format_ist(obs.observed_at),
            "created_at": format_ist(obs.created_at),
            "supersedes_id": obs.supersedes_id,
        }
    return TEMPLATES.TemplateResponse(request, "evidence.html", _ctx(request, o=data))


@app.get("/coverage", response_class=HTMLResponse)
def coverage(request: Request):
    reports = []
    with session_scope() as s:
        end = to_ist(now_utc()).date()
        start = end - timedelta(days=30)
        for name in ("Azadpur", "Keshopur"):
            m = s.scalar(select(Market).where(Market.canonical_name == name))
            if not m:
                continue
            rep = compute_coverage(s, market_id=m.id, start=start, end=end)
            reports.append(
                {
                    "market": rep.market,
                    "coverage": f"{rep.coverage_pct:.1%}",
                    "same_day": f"{rep.same_day_coverage_pct:.1%}",
                    "tracked": rep.tracked_commodities,
                    "verdict": r5_verdict(rep, is_live=True),
                }
            )
    return TEMPLATES.TemplateResponse(
        request, "coverage.html", _ctx(request, reports=reports, probe=_read_probe()[-14:])
    )


@app.get("/review", response_class=HTMLResponse)
def review_list(request: Request):
    with session_scope() as s:
        items = []
        for r in pending(s, limit=100):
            alias = s.get(Alias, r.alias_id)
            items.append(
                {
                    "id": r.id,
                    "alias": alias.alias_text,
                    "target": f"{alias.canonical_type.value}#{alias.canonical_id}",
                    "method": r.method or "manual",
                    "score": f"{float(r.score):.0f}" if r.score is not None else "—",
                }
            )
    return TEMPLATES.TemplateResponse(request, "review.html", _ctx(request, items=items))


@app.post("/review/{review_id}/approve")
def review_approve(review_id: int, reviewer: str = Form(...)):
    with session_scope() as s:
        approve(s, review_id, reviewer=reviewer or "web-user")
    return RedirectResponse("/review", status_code=303)


@app.get("/ingest", response_class=HTMLResponse)
def ingest_history(request: Request):
    with session_scope() as s:
        runs = []
        for r in s.scalars(select(IngestRun).order_by(IngestRun.started_at.desc()).limit(30)):
            runs.append(
                {
                    "id": r.id,
                    "when": format_ist(r.started_at),
                    "mode": r.mode,
                    "status": r.status,
                    "rows_in": r.rows_in,
                    "accepted": r.accepted,
                    "rejected": r.rejected,
                }
            )
    return TEMPLATES.TemplateResponse(request, "ingest.html", _ctx(request, runs=runs))


# --- JSON API (so every number traces to an API row) ---------------------------------
@app.get("/api/stats")
def api_stats():
    with session_scope() as s:
        return {
            "observations": s.scalar(select(func.count()).select_from(PriceObservation)) or 0,
            "commodities": s.scalar(select(func.count()).select_from(Commodity)) or 0,
            "markets": s.scalar(select(func.count()).select_from(Market)) or 0,
        }


@app.get("/api/observations/{obs_id}")
def api_observation(obs_id: int):
    with session_scope() as s:
        o = s.get(PriceObservation, obs_id)
        if o is None:
            return {"error": "not found"}
        return {
            "id": o.id,
            "commodity_id": o.commodity_id,
            "market_id": o.market_id,
            "source_class": o.source_class.value,
            "price_low_paise": o.price_low_paise,
            "price_high_paise": o.price_high_paise,
            "price_point_paise": o.price_point_paise,
            "canonical_price_paise_per_kg": o.canonical_price_paise_per_kg,
            "unit_raw": o.unit_raw,
            "source_url": o.source_url,
            "raw_quote": o.raw_quote,
            "observed_at": o.observed_at.isoformat(),
            "time_basis": o.time_basis.value,
        }


def _read_probe() -> list[dict]:
    path = REPO_ROOT / "data" / "coverage_probe.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [
            {**r, "total_rows": int(r["total_rows"]), "delhi_rows": int(r["delhi_rows"])}
            for r in csv.DictReader(fh)
        ]
