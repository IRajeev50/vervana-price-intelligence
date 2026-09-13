"""Supply-feed registry (M11): one honest status list for CLI and web.

Every supply-side feed reports what it is (fallback that works today vs partner
scaffold), whether it is configured, what it emits, and the exact next step. A
scaffold feed is always labelled scaffold - never implied to be live.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.config import Settings, get_settings
from vervana.models.context import ContextSignal
from vervana.supply.scaffold import FeedStatus


def collect_feed_status(settings: Settings | None = None) -> list[FeedStatus]:
    """Status of every supply-side feed, fallback first, scaffolds clearly marked."""
    from vervana.supply.alu import AluClient
    from vervana.supply.amed import AmedClient

    settings = settings or get_settings()

    cds_ok = bool(settings.cds_client_id and settings.cds_client_secret)
    sentinel = FeedStatus(
        name="sentinel2-ndvi",
        title="Sentinel-2 NDVI (Copernicus Data Space)",
        layer="fallback",
        configured=cds_ok,
        state=("configured" if cds_ok else "not configured - free CDSE OAuth client needed"),
        emits="ndvi_anomaly (production step)",
        hint=(
            "run: uv run vervana supply ndvi"
            if cds_ok
            else "register a free OAuth client at dataspace.copernicus.eu, set "
            "VERVANA_CDS_CLIENT_ID / VERVANA_CDS_CLIENT_SECRET"
        ),
        docs_url="https://documentation.dataspace.copernicus.eu/APIs/SentinelHub.html",
    )
    imd_ok = bool(settings.imd_district_rainfall_url)
    imd = FeedStatus(
        name="imd-rainfall",
        title="IMD district rainfall",
        layer="fallback",
        configured=True,  # the CSV import path always works
        state=("fetch URL configured" if imd_ok else "CSV import ready (no fetch URL set)"),
        emits="rainfall_deficit_pct (production step)",
        hint=(
            "run: uv run vervana supply rainfall-import <csv>"
            if not imd_ok
            else "fetch from VERVANA_IMD_DISTRICT_RAINFALL_URL or import CSV"
        ),
        docs_url="https://mausam.imd.gov.in/responsive/rainfallinformation.php",
    )

    return [sentinel, imd, AluClient(settings).status(), AmedClient(settings).status()]


def observed_supply_counts(session: Session) -> dict[str, int]:
    """Observed row counts for the supply-side signal kinds (display only)."""
    rows = session.execute(
        select(ContextSignal.signal_type, func.count())
        .where(
            ContextSignal.signal_type.in_(
                [
                    "ndvi_anomaly",
                    "rainfall_deficit_pct",
                    "acreage_change_pct",
                    "sowing_progress_pct",
                    "harvest_progress_pct",
                ]
            )
        )
        .group_by(ContextSignal.signal_type)
    ).all()
    return {kind: n for kind, n in rows}
