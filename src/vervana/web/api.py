"""Public API v1 (M8): authenticated, rate-limited, with B2B benchmarking and export.

Auth: an `X-API-Key` header checked against `VERVANA_PUBLIC_API_KEYS`. Rate limit: a
simple in-memory sliding window per key (per process — fine for the single-VPS design).
Every price carries provenance, source class and confidence, like the rest of the platform.
"""

from __future__ import annotations

import csv
import io
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from vervana.confidence import price_confidence
from vervana.config import get_settings
from vervana.db.engine import session_scope
from vervana.models.entities import Commodity, Market
from vervana.models.observations import PriceObservation

router = APIRouter(prefix="/api/v1", tags=["public"])

_hits: dict[str, deque] = defaultdict(deque)


def _valid_keys() -> set[str]:
    return {k.strip() for k in get_settings().public_api_keys.split(",") if k.strip()}


def require_api_key(x_api_key: str = Header(default="")) -> str:
    if x_api_key not in _valid_keys():
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
    # Rate limit: sliding 60s window.
    limit = get_settings().public_api_rate_per_min
    now = time.time()
    q = _hits[x_api_key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    q.append(now)
    return x_api_key


def _obs_dict(o: PriceObservation, cname: str, mname: str) -> dict:
    return {
        "id": o.id,
        "commodity": cname,
        "market": mname,
        "source_class": o.source_class.value,
        "price_low_paise": o.price_low_paise,
        "price_high_paise": o.price_high_paise,
        "canonical_price_paise_per_kg": o.canonical_price_paise_per_kg,
        "unit_raw": o.unit_raw,
        "confidence": price_confidence(o),
        "observed_at": o.observed_at.isoformat(),
        "source_url": o.source_url,
    }


@router.get("/prices")
def prices(
    commodity: str = "",
    market: str = "",
    limit: int = Query(100, le=1000),
    _key: str = Depends(require_api_key),
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
        rows = [_obs_dict(o, c, m) for o, c, m in s.execute(stmt.limit(limit))]
    return {"count": len(rows), "results": rows}


@router.get("/benchmark/{commodity}")
def benchmark(commodity: str, _key: str = Depends(require_api_key)):
    """B2B benchmark: latest ₹/kg for a commodity across every market (one source class,
    executed_summary — never blended with retail)."""
    from vervana.db.base import SourceClass

    with session_scope() as s:
        c = s.scalar(select(Commodity).where(Commodity.canonical_name == commodity))
        if c is None:
            raise HTTPException(404, f"unknown commodity '{commodity}'")
        rows = s.execute(
            select(PriceObservation, Market.canonical_name)
            .join(Market, Market.id == PriceObservation.market_id)
            .where(
                PriceObservation.commodity_id == c.id,
                PriceObservation.source_class == SourceClass.executed_summary,
                PriceObservation.canonical_price_paise_per_kg.is_not(None),
            )
            .order_by(PriceObservation.observed_at.desc())
        ).all()
        # latest per market
        seen: dict[str, dict] = {}
        for o, mname in rows:
            if mname not in seen:
                seen[mname] = {
                    "market": mname,
                    "rupees_per_kg": round(o.canonical_price_paise_per_kg / 100, 2),
                    "evidence_id": o.id,
                    "observed_at": o.observed_at.isoformat(),
                }
        markets = sorted(seen.values(), key=lambda r: r["rupees_per_kg"])
        prices_kg = [m["rupees_per_kg"] for m in markets]
        summary = None
        if prices_kg:
            summary = {
                "n_markets": len(prices_kg),
                "min": min(prices_kg),
                "max": max(prices_kg),
                "median": sorted(prices_kg)[len(prices_kg) // 2],
                "spread": round(max(prices_kg) - min(prices_kg), 2),
            }
    return {
        "commodity": commodity,
        "summary": summary,
        "markets": markets,
        "note": "executed_summary only; wholesale is never blended with retail.",
    }


@router.get("/forecast/status")
def forecast_status(_key: str = Depends(require_api_key)):
    from vervana.forecast import load_decision

    d = load_decision()
    return {
        "model_shippable": d.model_shippable,
        "serving": "model" if d.model_shippable else "baseline+interval",
        "reason": d.reason,
        "disclaimer": "Forecasts are an interval with a confidence, never a bare point. "
        "Not trading advice.",
    }


@router.get("/export")
def export(commodity: str = "", market: str = "", _key: str = Depends(require_api_key)):
    """Historical export as CSV (streamed)."""

    def rows():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "id",
                "commodity",
                "market",
                "source_class",
                "canonical_rupees_per_kg",
                "price_low_paise",
                "price_high_paise",
                "unit_raw",
                "observed_at",
                "source_url",
            ]
        )
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        with session_scope() as s:
            stmt = (
                select(PriceObservation, Commodity.canonical_name, Market.canonical_name)
                .join(Commodity, Commodity.id == PriceObservation.commodity_id)
                .join(Market, Market.id == PriceObservation.market_id)
                .order_by(PriceObservation.observed_at)
            )
            if commodity:
                stmt = stmt.where(Commodity.canonical_name == commodity)
            if market:
                stmt = stmt.where(Market.canonical_name == market)
            for o, cname, mname in s.execute(stmt):
                canon = (
                    ""
                    if o.canonical_price_paise_per_kg is None
                    else o.canonical_price_paise_per_kg / 100
                )
                w.writerow(
                    [
                        o.id,
                        cname,
                        mname,
                        o.source_class.value,
                        canon,
                        o.price_low_paise,
                        o.price_high_paise,
                        o.unit_raw,
                        o.observed_at.isoformat(),
                        o.source_url,
                    ]
                )
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vervana_export.csv"},
    )


@router.get("/intelligence/{commodity}")
def intelligence(commodity: str, _key: str = Depends(require_api_key)):
    """Signal-to-impact outlook for a commodity (M9). Inputs carry observed /
    simulated / missing labels; simulated inputs cap confidence. Not advice."""
    from vervana.intelligence import build_report

    with session_scope() as s:
        report = build_report(s, commodity)
    return report.to_dict()
@router.post("/admin/ingest/agmarknet")
def admin_ingest_agmarknet(
    state: str = "Delhi",
    max_records: int = Query(2000, le=10000),
    _key: str = Depends(require_api_key),
):
    """Trigger a live Agmarknet 2.0 ingest run.

    Deployed free-tier hosts have no shell, so this endpoint is how an operator (or a
    scheduler) kicks off a capture: it runs the same connector as
    `uv run vervana ingest agmarknet`. Idempotent per row: already-stored rows are
    skipped as duplicates, so a daily call is safe.
    """
    from vervana.connectors.agmarknet import AgmarknetConnector

    connector = AgmarknetConnector()
    if not connector.enabled():
        raise HTTPException(409, "connector 'agmarknet' is disabled via config")
    try:
        with session_scope() as session:
            run, result = connector.run(
                session, mode="daily", filters={"State": state}, max_records=max_records
            )
    except Exception as exc:
        with session_scope() as session:
            connector.record_failure(session, mode="daily", exc=exc)
        raise HTTPException(
            status_code=502, detail=f"ingest failed: {type(exc).__name__}: {exc}"
        ) from exc
    return {
        "run_id": run.id,
        "status": run.status,
        "rows_in": result.rows_in,
        "accepted": result.accepted,
        "rejected": result.rejected,
        "rejection_reasons": result.reason_counts,
    }
