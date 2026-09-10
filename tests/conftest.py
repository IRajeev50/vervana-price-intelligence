"""Shared test fixtures. All offline: in-memory SQLite, schema via metadata."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from vervana.db.base import Base
from vervana.models import Commodity, Market  # noqa: F401 - register tables


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = factory()
    try:
        yield s
    finally:
        # Tests operate within one session and rely on flush, not commit. Rolling back
        # on teardown keeps a test that deliberately triggered an IntegrityError from
        # poisoning teardown with a PendingRollbackError.
        s.rollback()
        s.close()
        engine.dispose()


@pytest.fixture
def potato_and_market(session: Session) -> tuple[int, int]:
    c = Commodity(canonical_name="Potato")
    m = Market(canonical_name="Azadpur", city="Delhi", state="Delhi")
    session.add_all([c, m])
    session.flush()
    return c.id, m.id
