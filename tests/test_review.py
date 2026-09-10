"""Review queue: pending enqueue, approve requires a reviewer, reject."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from vervana.db.base import AliasSourceType, CanonicalType, ReviewStatus
from vervana.models.entities import Commodity
from vervana.models.review import AliasReview
from vervana.repository.registry import add_alias
from vervana.repository.review import approve, pending, reject


def _enqueue(session: Session) -> int:
    c = Commodity(canonical_name="Potato")
    session.add(c)
    session.flush()
    alias = add_alias(
        session,
        alias_text="aloo",
        alias_language="hi-Latn",
        alias_source_type=AliasSourceType.hinglish_transliteration,
        canonical_type=CanonicalType.commodity,
        canonical_id=c.id,
        method="phonetic",
        score=92.0,
    )
    review = session.query(AliasReview).filter(AliasReview.alias_id == alias.id).one()
    return review.id


def test_new_alias_is_pending(session: Session):
    rid = _enqueue(session)
    items = pending(session)
    assert [r.id for r in items] == [rid]


def test_approve_requires_reviewer(session: Session):
    rid = _enqueue(session)
    with pytest.raises(ValueError, match="reviewer id is required"):
        approve(session, rid, reviewer="")


def test_approve_verifies_alias(session: Session):
    rid = _enqueue(session)
    alias = approve(session, rid, reviewer="rajeev")
    assert alias.is_verified
    assert alias.verified_by == "rajeev"
    review = session.get(AliasReview, rid)
    assert review.status == ReviewStatus.approved
    assert review.decided_by == "rajeev"
    assert pending(session) == []


def test_reject_leaves_alias_unverified(session: Session):
    rid = _enqueue(session)
    reject(session, rid, reviewer="rajeev", notes="wrong sense")
    review = session.get(AliasReview, rid)
    assert review.status == ReviewStatus.rejected
    from vervana.models.entities import Alias

    alias = session.get(Alias, review.alias_id)
    assert not alias.is_verified


def test_cannot_decide_twice(session: Session):
    rid = _enqueue(session)
    approve(session, rid, reviewer="rajeev")
    with pytest.raises(ValueError, match="already"):
        approve(session, rid, reviewer="rajeev")
