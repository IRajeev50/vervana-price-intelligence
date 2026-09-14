"""Engine and session factory, built from Settings.database_url."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from vervana.config import get_settings


def _create_engine(url: str) -> Engine:
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args.update({"check_same_thread": False, "timeout": 15})

    engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()

    return engine


@lru_cache(maxsize=1)
def _default_engine(url: str) -> Engine:
    """Keep one small pool for the serving process."""
    return _create_engine(url)


def make_engine(database_url: str | None = None) -> Engine:
    """Return the shared configured engine, or a fresh explicit test/tool engine."""
    if database_url is not None:
        return _create_engine(database_url)
    return _default_engine(get_settings().database_url)


@lru_cache(maxsize=1)
def _default_session_factory(url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=_default_engine(url), expire_on_commit=False, future=True)


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    if engine is not None:
        return sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return _default_session_factory(get_settings().database_url)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Transactional session scope: commit on success, roll back on error."""
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
