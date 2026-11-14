"""Flood overlay store: idempotent upsert on (zone, issued_time) + reads."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.models.flood_overlay import FloodOverlayRow
from vervana.supply.floodhub import SOURCE, FloodOverlay
from vervana.time import now_utc


def record_overlays(
    session: Session,
    overlays: list[FloodOverlay],
    *,
    source: str = SOURCE,
    source_url: str = "",
) -> dict[str, int]:
    """Append/refresh overlay rows, idempotent on (zone, issued_time)."""
    added = updated = 0
    retrieved = now_utc()
    for o in overlays:
        existing = session.execute(
            select(FloodOverlayRow).where(
                FloodOverlayRow.zone == o.zone,
                FloodOverlayRow.issued_time == o.issued_time,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                FloodOverlayRow(
                    zone=o.zone,
                    severity=o.severity,
                    trend=o.trend,
                    issued_time=o.issued_time,
                    valid_from=o.valid_from,
                    valid_to=o.valid_to,
                    source=source,
                    source_url=source_url,
                    retrieved_at=retrieved,
                )
            )
            added += 1
        else:
            existing.severity = o.severity
            existing.trend = o.trend
            existing.valid_from = o.valid_from
            existing.valid_to = o.valid_to
            existing.retrieved_at = retrieved
            updated += 1
    session.flush()
    return {"added": added, "updated": updated}


def latest_overlay_for_zone(session: Session, zone: str) -> FloodOverlayRow | None:
    return session.execute(
        select(FloodOverlayRow)
        .where(FloodOverlayRow.zone == zone)
        .order_by(FloodOverlayRow.issued_time.desc().nullslast(), FloodOverlayRow.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def overlay_count(session: Session) -> int:
    return int(session.execute(select(func.count(FloodOverlayRow.id))).scalar_one())
