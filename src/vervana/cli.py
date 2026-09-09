"""Vervana command-line entrypoint (Typer).

At M0 this proves the entrypoint, config load, and structured logging work. Real
ingest/serve/model commands are added in later milestones — this file is *not*
pre-scaffolded with empty stubs for them (Part 1.2).
"""

from __future__ import annotations

import typer

from vervana import __version__
from vervana.config import get_settings
from vervana.logging import configure_logging, get_logger

app = typer.Typer(
    add_completion=False,
    help="Vervana price-intelligence platform CLI.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def healthcheck() -> None:
    """Load config, emit one structured log line, confirm timezone policy.

    Exits 0 on success. Used by the smoke test and as a first deploy sanity check.
    """
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


if __name__ == "__main__":  # pragma: no cover
    app()
