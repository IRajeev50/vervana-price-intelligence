"""Vervana command-line entrypoint (Typer).

Commands grow milestone by milestone. M0: version, healthcheck. M1 adds the
`db`, `registry`, `review`, and `match` groups. This is the usable interface for the
registry + review queue (a junior operates it here, not by hand-editing SQL).
"""

from __future__ import annotations

from pathlib import Path

import typer

from vervana import __version__
from vervana.config import get_settings
from vervana.logging import configure_logging, get_logger

app = typer.Typer(
    add_completion=False,
    help="Vervana price-intelligence platform CLI.",
    no_args_is_help=True,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_DIR = REPO_ROOT / "data" / "seed"
EVAL_FILE = REPO_ROOT / "data" / "eval" / "aliases_200.csv"


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def healthcheck() -> None:
    """Load config, emit one structured log line, confirm timezone policy."""
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("vervana.healthcheck")
    log.info(
        "healthcheck",
        environment=settings.environment,
        timezone=settings.timezone,
        version=__version__,
    )
    if settings.timezone != "Asia/Kolkata":
        typer.echo(f"FAIL: timezone must be Asia/Kolkata, got {settings.timezone}", err=True)
        raise typer.Exit(code=1)
    typer.echo("ok")


# ---------------------------------------------------------------------------
# db
# ---------------------------------------------------------------------------
db_app = typer.Typer(help="Database migrations.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Run Alembic migrations up to REVISION (default head)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(cfg, revision)
    typer.echo(f"migrated to {revision}")


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
registry_app = typer.Typer(help="Entity registry.", no_args_is_help=True)
app.add_typer(registry_app, name="registry")


@registry_app.command("seed")
def registry_seed() -> None:
    """Seed commodities/varieties/markets from data/seed/*.csv."""
    from vervana.db.engine import session_scope
    from vervana.repository.registry import seed_registry

    with session_scope() as session:
        counts = seed_registry(session, SEED_DIR)
    for k, v in counts.items():
        typer.echo(f"{k:12} {v}")


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------
review_app = typer.Typer(help="Alias review queue.", no_args_is_help=True)
app.add_typer(review_app, name="review")


@review_app.command("list")
def review_list(limit: int = 20) -> None:
    """List pending alias reviews (highest matcher score first)."""
    from vervana.db.engine import session_scope
    from vervana.models.entities import Alias
    from vervana.repository.review import pending

    with session_scope() as session:
        items = pending(session, limit=limit)
        if not items:
            typer.echo("(no pending reviews)")
            return
        for r in items:
            alias = session.get(Alias, r.alias_id)
            score = f"{float(r.score):.1f}" if r.score is not None else "  - "
            typer.echo(
                f"review#{r.id}  score={score}  "
                f"'{alias.alias_text}' -> {alias.canonical_type.value}#{alias.canonical_id} "
                f"[{r.method or 'manual'}]"
            )


@review_app.command("approve")
def review_approve(review_id: int, reviewer: str = typer.Option(..., help="Reviewer id")) -> None:
    """Approve a pending review and verify its alias (requires a reviewer)."""
    from vervana.db.engine import session_scope
    from vervana.repository.review import approve

    with session_scope() as session:
        alias = approve(session, review_id, reviewer=reviewer)
        typer.echo(f"approved: alias#{alias.id} '{alias.alias_text}' verified by {reviewer}")


@review_app.command("reject")
def review_reject(review_id: int, reviewer: str = typer.Option(..., help="Reviewer id")) -> None:
    """Reject a pending review (alias stays unverified)."""
    from vervana.db.engine import session_scope
    from vervana.repository.review import reject

    with session_scope() as session:
        reject(session, review_id, reviewer=reviewer)
        typer.echo(f"rejected: review#{review_id} by {reviewer}")


# ---------------------------------------------------------------------------
# match
# ---------------------------------------------------------------------------
match_app = typer.Typer(help="Entity-resolution matching.", no_args_is_help=True)
app.add_typer(match_app, name="match")


@match_app.command("eval")
def match_eval(path: Path = EVAL_FILE) -> None:
    """Evaluate both matchers against the labelled alias set and print the report."""
    from vervana.matching.evaluate import evaluate, format_report, load_eval_rows

    rows = load_eval_rows(path)
    results = evaluate(rows)
    typer.echo(format_report(results))


if __name__ == "__main__":  # pragma: no cover
    app()
