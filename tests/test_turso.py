"""Turso engine selection while keeping local SQLite as the default."""

from unittest.mock import patch

import pytest

from vervana.db.engine import _default_engine, make_engine


def test_turso_env_selects_libsql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERVANA_TURSO_DATABASE_URL", "libsql://vervana-example.turso.io")
    monkeypatch.setenv("VERVANA_TURSO_AUTH_TOKEN", "test-token")
    _default_engine.cache_clear()
    with patch("vervana.db.engine.create_engine") as create:
        make_engine()
    create.assert_called_once_with(
        "sqlite+libsql://vervana-example.turso.io?secure=true",
        connect_args={"auth_token": "test-token"},
        future=True,
        pool_pre_ping=True,
    )
    _default_engine.cache_clear()


def test_turso_env_requires_url_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERVANA_TURSO_DATABASE_URL", "libsql://vervana-example.turso.io")
    monkeypatch.delenv("VERVANA_TURSO_AUTH_TOKEN", raising=False)
    _default_engine.cache_clear()
    with pytest.raises(RuntimeError, match="must be set together"):
        make_engine()
    _default_engine.cache_clear()


def test_explicit_sqlite_url_stays_local(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'local.sqlite3'}")
    assert engine.url.drivername == "sqlite"
