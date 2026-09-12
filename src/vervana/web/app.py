"""Vervana serving layer (M3): a browsable, provenance-first web app + JSON API.

Every displayed price links to its evidence (source_url + raw_quote) and shows its
source class and a confidence factor. The DMI accuracy disclaimer and GODL-India
attribution appear on every page (Part 7).
"""

from __future__ import annotations

import calendar as _calendar
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace as _NS

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from vervana.analytics.coverage import compute_coverage, r5_verdict
from vervana.confidence import price_confidence
from vervana.config import get_settings
from vervana.db.base import SourceClass
from vervana.db.engine import session_scope
from vervana.digest import build_digest
from vervana.models.entities import Alias, Commodity, Market
from vervana.models.ingest import IngestRun
from vervana.models.observations import PriceObservation
from vervana.models.review import AliasReview
from vervana.repository.review import approve, pending
from vervana.setup_status import collect_setup_steps
from vervana.time import format_ist, now_utc, to_ist

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

app = FastAPI(title="Vervana — Price Intelligence")

from vervana.web.api import router as api_v1_router  # noqa: E402

app.include_router(api_v1_router)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static",
)


def _paise_to_rupee(paise: int | None) -> str:
    return "—" if paise is None else f"₹{paise / 100:,.2f}"


def _confidence(obs: PriceObservation) -> float:
    return price_confidence(obs)


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
        setup_steps = collect_setup_steps(s, get_settings())
    probe = _read_probe()
    delhi_today = probe[-1]["delhi_rows"] if probe else "—"
    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        _ctx(
            request,
            stats=stats,
            last=last,
            delhi_today=delhi_today,
            probe_rows=len(probe),
            setup_steps=setup_steps,
            setup_all_ok=all(step.ok for step in setup_steps),
        ),
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
        total_observations = s.scalar(select(func.count()).select_from(PriceObservation)) or 0
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
            total_observations=total_observations,
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
        from vervana.confidence import price_confidence_full

        full_conf, agree_basis = price_confidence_full(s, obs)
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
            "confidence": full_conf,
            "confidence_basis": f"reliability × conversion × agreement ({agree_basis})",
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


@app.get("/benchmark", response_class=HTMLResponse)
def benchmark_page(request: Request, commodity: str = "Onion"):
    from vervana.db.base import SourceClass

    with session_scope() as s:
        commodities = [
            c
            for (c,) in s.execute(
                select(Commodity.canonical_name)
                .join(PriceObservation, PriceObservation.commodity_id == Commodity.id)
                .where(PriceObservation.source_class == SourceClass.executed_summary)
                .distinct()
                .order_by(Commodity.canonical_name)
            )
        ]
        rows = []
        c = s.scalar(select(Commodity).where(Commodity.canonical_name == commodity))
        if c is not None:
            seen = set()
            for o, mname in s.execute(
                select(PriceObservation, Market.canonical_name)
                .join(Market, Market.id == PriceObservation.market_id)
                .where(
                    PriceObservation.commodity_id == c.id,
                    PriceObservation.source_class == SourceClass.executed_summary,
                    PriceObservation.canonical_price_paise_per_kg.is_not(None),
                )
                .order_by(PriceObservation.observed_at.desc())
            ):
                if mname in seen:
                    continue
                seen.add(mname)
                rows.append(
                    {
                        "market": mname,
                        "rupees": f"{o.canonical_price_paise_per_kg / 100:,.2f}",
                        "value": o.canonical_price_paise_per_kg,
                        "id": o.id,
                    }
                )
            rows.sort(key=lambda r: r["value"])
    return TEMPLATES.TemplateResponse(
        request,
        "benchmark.html",
        _ctx(request, rows=rows, commodities=commodities, commodity=commodity),
    )


@app.get("/digest", response_class=HTMLResponse)
def digest_page(request: Request):
    with session_scope() as s:
        text = build_digest(s)
    return TEMPLATES.TemplateResponse(request, "digest.html", _ctx(request, digest=text))


@app.get("/forecast", response_class=HTMLResponse)
def forecast_page(request: Request):
    from vervana.forecast import load_decision
    from vervana.forecast.runner import prospective_summary

    with session_scope() as s:
        summary = prospective_summary(s)
    decision = load_decision()
    return TEMPLATES.TemplateResponse(
        request,
        "forecast.html",
        _ctx(request, decision=decision, summary=summary),
    )


# --- Agricultural intelligence (M9 + M10: portfolio, calendar, saved outlooks) ---
#
# No-lookahead rule (M10): past dates are served ONLY from the append-only
# intelligence_report store. The platform never recomputes what it "would have
# said" on a past date - historical analysis means the actual saved record,
# unedited. Generating an outlook is always a "now" action.


def _record_view(rec) -> _NS:
    """Normalise a stored report_json back into the shape intelligence.html uses."""
    d = json.loads(rec.report_json)

    def step_status(s: dict) -> str:
        if s.get("direction") == "unknown":
            return "insufficient evidence"
        sts = {i.get("status") for i in s.get("inputs", [])}
        if "simulated" in sts:
            return "simulated"
        if sts == {"observed"}:
            return "observed"
        return "derived"

    steps = [
        _NS(
            name=s["name"],
            finding=s["finding"],
            direction=_NS(value=s.get("direction", "unknown")),
            confidence=s.get("confidence", 0.0),
            status=step_status(s),
            missing=s.get("missing", []),
        )
        for s in d.get("steps", [])
    ]
    signals = [
        _NS(
            kind=g["kind"],
            region=g.get("region", ""),
            value_numeric=g.get("value_numeric"),
            value_text=g.get("value_text"),
            status=_NS(value=g.get("status", "missing")),
            source=g.get("source", ""),
            note=g.get("note", ""),
        )
        for g in d.get("signals", [])
    ]
    return _NS(
        commodity=d["commodity"],
        made_at_utc=d["made_at_utc"],
        horizon=_NS(label=d["horizon"]["label"], basis=d["horizon"]["basis"]),
        verdict=d["verdict"],
        verdict_reason=d["verdict_reason"],
        n_observed=d["n_observed"],
        n_simulated=d["n_simulated"],
        n_missing=d["n_missing"],
        confidence=d["confidence"],
        steps=steps,
        signals=signals,
        price_context=d.get("price_context", {}),
    )


def _regions_for(signals) -> list[str]:
    return sorted({g.region for g in signals if g.region and g.status.value != "missing"})


@app.get("/intelligence", response_class=HTMLResponse)
def intelligence_index(request: Request):
    from vervana.intelligence.crops import forecast_horizon, load_profiles
    from vervana.models.intelligence import IntelligenceReportRecord

    profiles = load_profiles()
    horizons = [forecast_horizon(p) for p in profiles.values()]
    with session_scope() as s:
        latest: dict = {}
        for rec in s.scalars(
            select(IntelligenceReportRecord).order_by(IntelligenceReportRecord.made_at.desc())
        ):
            latest.setdefault(rec.commodity, rec)
        crops = []
        for name, profile in profiles.items():
            h = forecast_horizon(profile)
            rec = latest.get(name)
            info = None
            if rec is not None:
                d = json.loads(rec.report_json)
                direction = next(
                    (
                        st.get("direction", "unknown")
                        for st in d.get("steps", [])
                        if st.get("name") == "price_pressure"
                    ),
                    "unknown",
                )
                alerts = []
                if rec.n_simulated:
                    alerts.append({"tone": "warn", "text": "simulated inputs cap confidence"})
                if rec.n_missing:
                    alerts.append({"tone": "missing", "text": f"{rec.n_missing} missing input(s)"})
                info = {
                    "id": rec.id,
                    "verdict": rec.verdict,
                    "confidence": rec.confidence,
                    "n_observed": rec.n_observed,
                    "n_simulated": rec.n_simulated,
                    "n_missing": rec.n_missing,
                    "direction": direction,
                    "made_at_ist": format_ist(rec.made_at),
                    "alerts": alerts,
                }
            crops.append(
                {
                    "commodity": name,
                    "horizon_label": h.label,
                    "horizon_basis": h.basis,
                    "latest": info,
                }
            )
    return TEMPLATES.TemplateResponse(
        request,
        "intelligence_index.html",
        _ctx(request, crops=crops, horizons=horizons),
    )


def _month_nav(month: str) -> tuple[int, int, str, str]:
    year, mon = int(month[:4]), int(month[5:7])
    prev_y, prev_m = (year - 1, 12) if mon == 1 else (year, mon - 1)
    next_y, next_m = (year + 1, 1) if mon == 12 else (year, mon + 1)
    return prev_y, prev_m, f"{prev_y:04d}-{prev_m:02d}", f"{next_y:04d}-{next_m:02d}"


def _history_page(request: Request, month: str, commodity: str, day: date | None):
    from vervana.intelligence.crops import load_profiles
    from vervana.models.intelligence import IntelligenceReportRecord

    try:
        date(int(month[:4]), int(month[5:7]), 1)
        if len(month) != 7 or month[4] != "-":
            raise ValueError
    except (ValueError, IndexError):
        month = to_ist(now_utc()).strftime("%Y-%m")
    _, _, prev_month, next_month = _month_nav(month)

    with session_scope() as s:
        stmt = select(IntelligenceReportRecord).order_by(IntelligenceReportRecord.made_at)
        if commodity:
            stmt = stmt.where(IntelligenceReportRecord.commodity == commodity)
        recs = list(s.scalars(stmt))

    by_day: dict[date, list] = {}
    for r in recs:
        by_day.setdefault(to_ist(r.made_at).date(), []).append(r)

    year, mon = int(month[:4]), int(month[5:7])
    today = to_ist(now_utc()).date()
    if day is None and (year, mon) == (today.year, today.month):
        day = today

    cells = []
    for week in _calendar.monthcalendar(year, mon):
        for dnum in week:
            if dnum == 0:
                cells.append({"day": None})
            else:
                d = date(year, mon, dnum)
                cells.append(
                    {
                        "day": dnum,
                        "iso": d.isoformat(),
                        "count": len(by_day.get(d, [])),
                        "is_today": d == today,
                    }
                )

    day_records = []
    if day is not None:
        for r in by_day.get(day, []):
            day_records.append(
                {
                    "id": r.id,
                    "commodity": r.commodity,
                    "made_at_ist": format_ist(r.made_at),
                    "verdict": r.verdict,
                    "confidence": r.confidence,
                    "n_observed": r.n_observed,
                    "n_simulated": r.n_simulated,
                    "n_missing": r.n_missing,
                }
            )

    month_label = date(year, mon, 1).strftime("%B %Y")
    return TEMPLATES.TemplateResponse(
        request,
        "intelligence_history.html",
        _ctx(
            request,
            month=month,
            month_label=month_label,
            prev_month=prev_month,
            next_month=next_month,
            cells=cells,
            day=day.day if day else None,
            day_label=day.strftime("%A, %-d %B %Y") if day else None,
            records=day_records,
            n_records=sum(len(v) for k, v in by_day.items() if k.month == mon and k.year == year),
            commodities=list(load_profiles().keys()),
            commodity=commodity,
        ),
    )


@app.get("/intelligence/history", response_class=HTMLResponse)
def intelligence_history(request: Request, month: str = "", commodity: str = ""):
    month = month or to_ist(now_utc()).strftime("%Y-%m")
    return _history_page(request, month, commodity, None)


@app.get("/intelligence/history/{day}", response_class=HTMLResponse)
def intelligence_history_day(request: Request, day: str, commodity: str = ""):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return HTMLResponse("<h1>404 — not a date (YYYY-MM-DD)</h1>", status_code=404)
    return _history_page(request, d.strftime("%Y-%m"), commodity, d)


@app.get("/intelligence/record/{rec_id}", response_class=HTMLResponse)
def intelligence_record(request: Request, rec_id: int):
    from vervana.models.intelligence import IntelligenceReportRecord

    with session_scope() as s:
        rec = s.get(IntelligenceReportRecord, rec_id)
        if rec is None:
            return HTMLResponse("<h1>404 — no such saved outlook</h1>", status_code=404)
        report = _record_view(rec)
        record = _NS(id=rec.id, made_at_ist=format_ist(rec.made_at))
    return TEMPLATES.TemplateResponse(
        request,
        "intelligence.html",
        _ctx(
            request,
            report=report,
            signals=report.signals,
            regions=_regions_for(report.signals),
            region="",
            stored=True,
            record=record,
        ),
    )


@app.post("/intelligence/{commodity}/save")
def intelligence_save(commodity: str):
    from vervana.intelligence import build_report, save_record

    with session_scope() as s:
        report = build_report(s, commodity)
        rec_id = save_record(s, report)
    return RedirectResponse(f"/intelligence/record/{rec_id}", status_code=303)


@app.get("/intelligence/{commodity}", response_class=HTMLResponse)
def intelligence_detail(request: Request, commodity: str, region: str = ""):
    from vervana.intelligence import build_report

    with session_scope() as s:
        report = build_report(s, commodity)
    signals = report.signals
    if region:
        signals = [g for g in signals if g.region == region]
    return TEMPLATES.TemplateResponse(
        request,
        "intelligence.html",
        _ctx(
            request,
            report=report,
            signals=signals,
            regions=_regions_for(report.signals),
            region=region,
            stored=False,
            record=None,
        ),
    )


@app.get("/api/intelligence/records/{rec_id}")
def api_intelligence_record(rec_id: int):
    from vervana.models.intelligence import IntelligenceReportRecord

    with session_scope() as s:
        rec = s.get(IntelligenceReportRecord, rec_id)
        if rec is None:
            return {"error": "not found"}
        return {
            "id": rec.id,
            "commodity": rec.commodity,
            "made_at": rec.made_at.isoformat(),
            "horizon_label": rec.horizon_label,
            "verdict": rec.verdict,
            "n_observed": rec.n_observed,
            "n_simulated": rec.n_simulated,
            "n_missing": rec.n_missing,
            "confidence": rec.confidence,
            "report": json.loads(rec.report_json),
        }




@app.get("/intelligence/{commodity}/report.pdf")
def intelligence_pdf(commodity: str):
    from vervana.intelligence.report import build_report
    from vervana.policy import render_intelligence_pdf
    with session_scope() as session:
        report = build_report(session, commodity)
    body = render_intelligence_pdf(report.to_dict())
    filename = f"v-ai-{commodity.lower().replace(' ', '-')}-intelligence.pdf"
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.get("/api/policy-impact/{commodity}")
def api_policy_impact(commodity: str):
    from vervana.policy import build_policy_impact
    from vervana.intelligence.report import build_report
    with session_scope() as session:
        price_context = build_report(session, commodity).price_context
    return build_policy_impact(commodity, price_context)


@app.get("/policy-impact/{commodity}", response_class=HTMLResponse)
def policy_impact_page(request: Request, commodity: str):
    from vervana.policy import build_policy_impact
    from vervana.intelligence.report import build_report
    with session_scope() as session:
        price_context = build_report(session, commodity).price_context
    impact = build_policy_impact(commodity, price_context)
    return TEMPLATES.TemplateResponse(request, "policy_impact.html", _ctx(request, impact=impact))


@app.get("/policy-impact/{commodity}/report.pdf")
def policy_impact_pdf(commodity: str):
    from vervana.policy import build_policy_impact, render_policy_pdf
    from vervana.intelligence.report import build_report
    with session_scope() as session:
        price_context = build_report(session, commodity).price_context
    body = render_policy_pdf(build_policy_impact(commodity, price_context))
    filename = f"v-ai-{commodity.lower().replace(' ', '-')}-policy-impact.pdf"
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

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
