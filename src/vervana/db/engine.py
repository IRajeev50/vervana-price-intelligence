"""Engine and session factory, built from Settings.database_url."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from vervana.config import get_settings


def _create_engine(
    url: str,
    *,
    turso_database_url: str | None = None,
    turso_auth_token: str | None = None,
) -> Engine:
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    is_turso = bool(turso_database_url and turso_auth_token)
    if is_turso:
        remote_url = turso_database_url.removeprefix("libsql://")
        url = f"sqlite+libsql://{remote_url}?secure=true"
        connect_args["auth_token"] = turso_auth_token
    elif url.startswith("sqlite"):
        connect_args.update({"check_same_thread": False, "timeout": 15})

    engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
    if url.startswith("sqlite") and not is_turso:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()

    return engine


@lru_cache(maxsize=1)
def _default_engine(
    url: str, turso_database_url: str | None, turso_auth_token: str | None
) -> Engine:
    """Keep one small pool for the serving process."""
    if bool(turso_database_url) != bool(turso_auth_token):
        raise RuntimeError(
            "VERVANA_TURSO_DATABASE_URL and VERVANA_TURSO_AUTH_TOKEN must be set together"
        )
    return _create_engine(
        url, turso_database_url=turso_database_url, turso_auth_token=turso_auth_token
    )


def make_engine(database_url: str | None = None) -> Engine:
    """Return the shared configured engine, or a fresh explicit test/tool engine."""
    if database_url is not None:
        return _create_engine(database_url)
    settings = get_settings()
    return _default_engine(
        settings.database_url, settings.turso_database_url, settings.turso_auth_token
    )


@lru_cache(maxsize=1)
def _default_session_factory(
    url: str, turso_database_url: str | None, turso_auth_token: str | None
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=_default_engine(url, turso_database_url, turso_auth_token),
        expire_on_commit=False,
        future=True,
    )


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    if engine is not None:
        return sessionmaker(bind=engine, expire_on_commit=False, future=True)
    settings = get_settings()
    return _default_session_factory(
        settings.database_url, settings.turso_database_url, settings.turso_auth_token
    )


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
