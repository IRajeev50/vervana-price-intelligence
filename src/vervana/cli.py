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


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------
ingest_app = typer.Typer(help="Data-source ingestion.", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")


@ingest_app.command("agmarknet")
def ingest_agmarknet(
    mode: str = "daily",
    state: str = "Delhi",
    max_records: int = 1000,
) -> None:
    """Fetch live Agmarknet data (needs VERVANA_DATA_GOV_IN_API_KEY) and ingest it."""
    from vervana.connectors.agmarknet import AgmarknetConnector
    from vervana.db.engine import session_scope

    connector = AgmarknetConnector()
    if not connector.enabled():
        typer.echo(f"connector '{connector.name}' is disabled via config; nothing to do")
        return
    with session_scope() as session:
        run, result = connector.run(
            session, mode=mode, filters={"State": state}, max_records=max_records
        )
    typer.echo(
        f"ingest_run#{run.id} {run.status}: in={result.rows_in} "
        f"accepted={result.accepted} rejected={result.rejected}"
    )
    for reason, count in result.reason_counts.items():
        typer.echo(f"  rejected [{count}]: {reason}")


@ingest_app.command("agmarknet-file")
def ingest_agmarknet_file(path: Path) -> None:
    """Ingest a locally-saved Agmarknet JSON payload (offline; a records[] array or envelope)."""
    import json

    from vervana.connectors.agmarknet import AgmarknetConnector
    from vervana.db.engine import session_scope

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("records", payload) if isinstance(payload, dict) else payload
    connector = AgmarknetConnector()
    with session_scope() as session:
        run, result = connector.ingest_with_run(
            session, records, mode="file", raw_payload_path=path
        )
    typer.echo(
        f"ingest_run#{run.id} {run.status}: in={result.rows_in} "
        f"accepted={result.accepted} rejected={result.rejected}"
    )
    for reason, count in sorted(result.reason_counts.items(), key=lambda kv: -kv[1])[:8]:
        typer.echo(f"  rejected [{count}]: {reason}")


@ingest_app.command("history")
def ingest_history(limit: int = 20) -> None:
    """Show recent ingest runs — the daily-capture history (R5 coverage over time)."""
    from sqlalchemy import select

    from vervana.db.engine import session_scope
    from vervana.models.ingest import IngestRun
    from vervana.time import format_ist

    with session_scope() as session:
        runs = list(
            session.scalars(select(IngestRun).order_by(IngestRun.started_at.desc()).limit(limit))
        )
        if not runs:
            typer.echo("(no ingest runs yet)")
            return
        for r in runs:
            typer.echo(
                f"run#{r.id:<4} {format_ist(r.started_at)}  {r.connector}/{r.mode:<8} "
                f"{r.status:<7} in={r.rows_in} accepted={r.accepted} rejected={r.rejected}"
            )


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------
coverage_app = typer.Typer(help="Coverage study (R5).", no_args_is_help=True)
app.add_typer(coverage_app, name="coverage")


@coverage_app.command("report")
def coverage_report(
    market: str = "Azadpur",
    days: int = 90,
    live: bool = typer.Option(
        False, help="Assert the data is from the LIVE API (real R5 verdict)."
    ),
) -> None:
    """Run the Agmarknet Delhi coverage study for a market over the last N days."""
    from datetime import timedelta

    from sqlalchemy import select

    from vervana.analytics.coverage import compute_coverage, format_report
    from vervana.db.engine import session_scope
    from vervana.models.entities import Market
    from vervana.time import now_utc, to_ist

    with session_scope() as session:
        m = session.scalar(select(Market).where(Market.canonical_name == market))
        if m is None:
            typer.echo(f"unknown market '{market}' (seed the registry first)", err=True)
            raise typer.Exit(code=1)
        end = to_ist(now_utc()).date()
        start = end - timedelta(days=days - 1)
        report = compute_coverage(session, market_id=m.id, start=start, end=end)
        typer.echo(format_report(report, is_live=live))


if __name__ == "__main__":  # pragma: no cover
    app()
