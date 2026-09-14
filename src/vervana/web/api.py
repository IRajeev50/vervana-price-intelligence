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
from datetime import date


from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
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
@router.post("/admin/ingest/youtube-ground-proof")
async def admin_ingest_youtube_ground_proof(
    file: UploadFile = File(...),
    _key: str = Depends(require_api_key),
):
    """Import a provenance-preserving YouTube mandi CSV/XLSX upload."""
    from vervana.connectors.transcript import TranscriptConnector

    content = await file.read()
    if not content:
        raise HTTPException(422, "empty upload")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "upload exceeds 10 MB")
    connector = TranscriptConnector()
    try:
        records = connector.records_from_upload(file.filename or "", content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if not records:
        raise HTTPException(422, "no data rows found")
    with session_scope() as session:
        run, result = connector.ingest_with_run(session, records, mode="admin_upload")
    return {
        "run_id": run.id, "status": run.status,
        "source_type": "youtube_ground_proof", "source_class": "quote_indicative",
        "rows_in": result.rows_in, "accepted": result.accepted,
        "skipped": result.rejected, "skip_reasons": result.reason_counts,
    }


@router.post("/admin/ingest/agmarknet")
def admin_ingest_agmarknet(
    state: str = "Delhi",
    # Big states report ~1.4k flattened rows/day (all markets x commodities), so a
    # 31-day chunk needs headroom far above the old 10k cap; registry filtering keeps
    # only seeded markets/commodities, so accepted rows stay bounded.
    max_records: int = Query(5000, le=250000),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _key: str = Depends(require_api_key),
):
    """Trigger a live Agmarknet 2.0 ingest run.

    Deployed free-tier hosts have no shell, so this endpoint is how an operator (or a
    scheduler) kicks off a capture: it runs the same connector as
    `uv run vervana ingest agmarknet`. Idempotent per row: already-stored rows are
    skipped as duplicates, so a daily call is safe.
    """
    from vervana.connectors.agmarknet import AgmarknetConnector

    if (start_date is None) != (end_date is None):
        raise HTTPException(422, "start_date and end_date must be provided together")
    if start_date is not None:
        if start_date > end_date:
            raise HTTPException(422, "start_date must be on or before end_date")
        if (end_date - start_date).days > 30:
            raise HTTPException(422, "historical backfill chunks are limited to 31 days")

    connector = AgmarknetConnector()
    if not connector.enabled():
        raise HTTPException(409, "connector 'agmarknet' is disabled via config")
    try:
        with session_scope() as session:
            run, result = connector.run(
                session,
                mode="backfill" if start_date is not None else "daily",
                filters={"State": state},
                max_records=max_records,
                start_date=start_date,
                end_date=end_date,
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


@router.post("/admin/supply/ndvi")
def admin_supply_ndvi(
    zone: str = "",
    days: int = Query(30, ge=7, le=120),
    _key: str = Depends(require_api_key),
):
    """Fetch Sentinel-2 NDVI for the watch zones and ingest anomaly signals.

    Same code path as `uv run vervana supply ndvi`; this endpoint exists because
    deployed free-tier hosts have no shell. Requires VERVANA_CDS_CLIENT_ID and
    VERVANA_CDS_CLIENT_SECRET - without them nothing is fetched and nothing is
    faked (409). Rows already stored for a date can repeat; the NDVI connector
    has no dedupe key, so call it on a daily cadence at most.
    """
    from datetime import timedelta

    from vervana.connectors.sentinel2 import Sentinel2NdviConnector
    from vervana.supply.zones import load_zones
    from vervana.time import now_utc

    zones = load_zones()
    if zone:
        zones = [z for z in zones if z.zone == zone]
        if not zones:
            raise HTTPException(404, f"unknown zone '{zone}'")
    conn = Sentinel2NdviConnector()
    if not conn.enabled():
        raise HTTPException(
            409,
            "sentinel2-ndvi is not configured - set VERVANA_CDS_CLIENT_ID and "
            "VERVANA_CDS_CLIENT_SECRET",
        )
    today = now_utc().date()
    current_from, current_to = today - timedelta(days=days), today
    baseline_from = current_from.replace(year=current_from.year - 1)
    baseline_to = current_to.replace(year=current_to.year - 1)
    try:
        records = conn.fetch_raw(
            zones=zones,
            current_from=current_from,
            current_to=current_to,
            baseline_from=baseline_from,
            baseline_to=baseline_to,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"ndvi fetch failed: {type(exc).__name__}: {exc}"
        ) from exc
    with session_scope() as session:
        run, result = conn.ingest_with_run(session, records, mode="api")
    return {
        "run_id": run.id,
        "status": run.status,
        "rows_in": result.rows_in,
        "accepted": result.accepted,
        "rejected": result.rejected,
        "rejection_reasons": result.reason_counts,
    }


@router.post("/admin/supply/rainfall")
async def admin_supply_rainfall(
    request: Request,
    _key: str = Depends(require_api_key),
):
    """Import IMD district rainfall as observed rainfall_deficit_pct signals.

    Body: CSV text with columns district,state,date and dep_pct (or
    actual_mm+normal_mm) - the same rows `uv run vervana supply rainfall-import`
    accepts. With an empty body it fetches VERVANA_IMD_DISTRICT_RAINFALL_URL when
    configured; IMD's public district bulletin is a PDF, so the CSV body is the
    path that works today.
    """
    from vervana.connectors.imd import ImdRainfallConnector

    conn = ImdRainfallConnector()
    body = (await request.body()).decode("utf-8", errors="replace").strip()
    try:
        if body:
            records = list(csv.DictReader(io.StringIO(body)))
        else:
            records = conn.fetch_raw()
    except NotImplementedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"rainfall fetch failed: {type(exc).__name__}: {exc}",
        ) from exc
    records = [r for r in records if any((v or "").strip() for v in r.values())]
    if not records:
        raise HTTPException(422, "no rows: send CSV text in the request body")
    with session_scope() as session:
        run, result = conn.ingest_with_run(session, records, mode="api")
    return {
        "run_id": run.id,
        "status": run.status,
        "rows_in": result.rows_in,
        "accepted": result.accepted,
        "rejected": result.rejected,
        "rejection_reasons": result.reason_counts,
    }

@router.post("/admin/registry/seed")
def admin_registry_seed(_key: str = Depends(require_api_key)):
    """Idempotently seed the canonical registry from the checked-in CSVs.

    Deployed free-tier hosts have no shell, so a deploy that adds seed commodities
    or markets cannot run `uv run vervana registry seed` there - this endpoint is
    the operator path. seed_registry is get-or-create, so repeat calls only add
    what is missing; live prices still come from ingest runs, never from the seed.
    """
    from pathlib import Path

    from vervana.repository.registry import seed_registry

    seed_dir = Path(__file__).resolve().parents[3] / "data" / "seed"
    with session_scope() as session:
        counts = seed_registry(session, seed_dir)
    return {"seeded": True, "counts": counts}
