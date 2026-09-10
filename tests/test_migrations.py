"""Alembic migration round-trips on a temp SQLite file (offline)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).resolve().parent.parent


def _config(db_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_then_downgrade(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "m.sqlite3"
    db_url = f"sqlite:///{db_file}"
    # env.py reads the URL from settings; point settings at this temp db.
    monkeypatch.setenv("VERVANA_DATABASE_URL", db_url)
    cfg = _config(db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(db_url, future=True)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {"price_observation", "commodity", "alias", "unit_convention"} <= tables

    command.downgrade(cfg, "base")
    engine = create_engine(db_url, future=True)
    remaining = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "price_observation" not in remaining
