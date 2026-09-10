"""Review-queue operations. Promotion to verified requires a recorded reviewer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.db.base import ReviewStatus
from vervana.models.entities import Alias
from vervana.models.review import AliasReview
from vervana.time import now_utc


def pending(session: Session, limit: int | None = None) -> list[AliasReview]:
    stmt = (
        select(AliasReview)
        .where(AliasReview.status == ReviewStatus.pending)
        .order_by(AliasReview.score.desc().nullslast(), AliasReview.id)
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def approve(session: Session, review_id: int, *, reviewer: str, notes: str | None = None) -> Alias:
    """Approve a pending review: mark it approved AND verify the underlying alias.

    A reviewer id is mandatory — an alias is never promoted anonymously.
    """
    if not reviewer or not reviewer.strip():
        raise ValueError("a reviewer id is required to approve an alias")
    review = _get_pending(session, review_id)
    alias = session.get(Alias, review.alias_id)
    if alias is None:
        raise ValueError(f"review {review_id} points to missing alias {review.alias_id}")

    now = now_utc()
    review.status = ReviewStatus.approved
    review.decided_by = reviewer
    review.decided_at = now
    review.notes = notes
    alias.verified_by = reviewer
    alias.verified_at = now
    session.flush()
    return alias


def reject(session: Session, review_id: int, *, reviewer: str, notes: str | None = None) -> None:
    """Reject a pending review. The alias stays unverified (never resolves)."""
    if not reviewer or not reviewer.strip():
        raise ValueError("a reviewer id is required to reject an alias")
    review = _get_pending(session, review_id)
    review.status = ReviewStatus.rejected
    review.decided_by = reviewer
    review.decided_at = now_utc()
    review.notes = notes
    session.flush()


def _get_pending(session: Session, review_id: int) -> AliasReview:
    review = session.get(AliasReview, review_id)
    if review is None:
        raise ValueError(f"no review with id={review_id}")
    if review.status != ReviewStatus.pending:
        raise ValueError(f"review {review_id} is already {review.status.value}")
    return review
