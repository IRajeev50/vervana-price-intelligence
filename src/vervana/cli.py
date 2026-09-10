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


@registry_app.command("sync-mandis")
def registry_sync_mandis(path: Path = REPO_ROOT / "data" / "config" / "mandis.csv") -> None:
    """Add mandis from the config file (adding a mandi is a config change, not code).

    Emits the R12 observer-cost estimate for the configured headcount.
    """
    from vervana.db.engine import session_scope
    from vervana.economics import estimate_observer_cost
    from vervana.repository.registry import sync_mandis

    with session_scope() as session:
        res = sync_mandis(session, path)
    typer.echo(f"mandis in config: {res['n_mandis']} · newly added: {res['added']}")
    est = estimate_observer_cost(res["n_mandis"], observers_per_mandi=1)
    # Use the configured total observer headcount for a truer estimate.
    est_real = estimate_observer_cost(1, observers_per_mandi=res["total_observers"] or 0)
    typer.echo(est_real.as_lines() if res["total_observers"] else est.as_lines())


@registry_app.command("bootstrap")
def registry_bootstrap(path: Path) -> None:
    """Create commodities/markets from a live Agmarknet snapshot's official names."""
    import json

    from vervana.db.engine import session_scope
    from vervana.repository.registry import bootstrap_from_agmarknet_records

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("records", payload) if isinstance(payload, dict) else payload
    with session_scope() as session:
        created = bootstrap_from_agmarknet_records(session, records)
    typer.echo(f"created commodities={created['commodity']} markets={created['market']}")


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


@ingest_app.command("qcomm-csv")
def ingest_qcomm_csv(path: Path) -> None:
    """Import quick-commerce retail prices from a manual-panel CSV (no scraping)."""
    from vervana.connectors.quickcommerce import QuickCommerceConnector
    from vervana.db.engine import session_scope

    with session_scope() as session:
        result = QuickCommerceConnector().import_csv(session, path)
    typer.echo(f"in={result.rows_in} accepted={result.accepted} rejected={result.rejected}")
    for reason, count in sorted(result.reason_counts.items(), key=lambda kv: -kv[1]):
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


@ingest_app.command("observer-csv")
def ingest_observer_csv(path: Path) -> None:
    """Import field-observer quotes from a CSV (each carries observer independence)."""
    from vervana.connectors.observer import ObserverConnector
    from vervana.db.engine import session_scope

    with session_scope() as session:
        result = ObserverConnector().import_csv(session, path)
    typer.echo(f"in={result.rows_in} accepted={result.accepted} rejected={result.rejected}")
    for reason, count in sorted(result.reason_counts.items(), key=lambda kv: -kv[1]):
        typer.echo(f"  rejected [{count}]: {reason}")


@ingest_app.command("context-csv")
def ingest_context_csv(path: Path) -> None:
    """Import context signals (weather/diesel/festival) from a CSV — model features."""
    from vervana.connectors.context import ContextConnector
    from vervana.db.engine import session_scope

    with session_scope() as session:
        result = ContextConnector().import_csv(session, path)
    typer.echo(f"in={result.rows_in} accepted={result.accepted} rejected={result.rejected}")


@ingest_app.command("transcript-csv")
def ingest_transcript_csv(path: Path) -> None:
    """Import the human-curated video-quote corpus (M6; quote_indicative, R3/R8)."""
    import csv as _csv

    from vervana.connectors.transcript import TranscriptConnector
    from vervana.db.engine import session_scope

    with Path(path).open(encoding="utf-8") as fh:
        records = list(_csv.DictReader(fh))
    with session_scope() as session:
        run, result = TranscriptConnector().ingest_with_run(
            session, records, mode="transcript", raw_payload_path=str(path)
        )
    typer.echo(
        f"ingest_run#{run.id}: in={result.rows_in} accepted={result.accepted} "
        f"rejected={result.rejected}"
    )
    for reason, count in sorted(result.reason_counts.items(), key=lambda kv: -kv[1])[:8]:
        typer.echo(f"  rejected [{count}]: {reason}")


@ingest_app.command("enam")
def ingest_enam() -> None:
    """eNAM connector (stub — no open API yet; see OPEN_QUESTIONS #1)."""
    from vervana.connectors.enam import EnamAccessUnresolvedError, EnamConnector

    try:
        EnamConnector().fetch_raw()
    except EnamAccessUnresolvedError as exc:
        typer.echo(f"eNAM unavailable: {exc}")


# ---------------------------------------------------------------------------
# forecast
# ---------------------------------------------------------------------------
forecast_app = typer.Typer(
    help="Forecasting harness (baselines + models + kill).", no_args_is_help=True
)
app.add_typer(forecast_app, name="forecast")


@forecast_app.command("demo")
def forecast_demo(kind: str = "randomwalk") -> None:
    """Run the harness on a synthetic series (randomwalk|seasonal) — shows the kill check."""
    import numpy as np

    from vervana.forecast import backtest_all, format_backtest, summarize_and_persist

    rng = np.random.default_rng(0)
    if kind == "seasonal":
        t = np.arange(160)
        series = 2000 + 300 * np.sin(2 * np.pi * t / 7) + rng.normal(0, 15, 160)
    else:
        series = 2000 + np.cumsum(rng.normal(0, 40, 120))
    results = backtest_all(series, min_train=21)
    typer.echo(format_backtest(results))
    summary = summarize_and_persist(results)
    typer.echo(f"\nmodel_shippable: {summary['model_shippable']}")
    typer.echo(summary["kill_reason"])


@forecast_app.command("backtest")
def forecast_backtest(commodity: str, market: str = "Azadpur", source: str = "quote") -> None:
    """Real walk-forward backtest for a commodity+market series from the DB."""
    from sqlalchemy import select

    from vervana.db.engine import session_scope
    from vervana.forecast import backtest_all, format_backtest, summarize_and_persist
    from vervana.forecast.series import price_series, quote_midpoint_series
    from vervana.models.entities import Commodity, Market

    with session_scope() as session:
        c = session.scalar(select(Commodity).where(Commodity.canonical_name == commodity))
        m = session.scalar(select(Market).where(Market.canonical_name == market))
        if not c or not m:
            typer.echo("unknown commodity/market", err=True)
            raise typer.Exit(1)
        if source == "quote":
            series = quote_midpoint_series(session, commodity_id=c.id, market_id=m.id)
        else:
            series = price_series(session, commodity_id=c.id, market_id=m.id)
        typer.echo(f"{commodity} @ {market} ({source}): {len(series)} daily points")
        if len(series) <= 21:
            typer.echo("not enough history yet (need > 21 days).")
            raise typer.Exit(0)
        results = backtest_all(series, min_train=21)
        typer.echo(format_backtest(results))
        summary = summarize_and_persist(results)
        typer.echo(f"\nmodel_shippable: {summary['model_shippable']}\n{summary['kill_reason']}")


@forecast_app.command("status")
def forecast_status() -> None:
    """Show the current kill decision (what the serving layer would expose)."""
    from vervana.forecast import load_decision

    d = load_decision()
    typer.echo(f"model_shippable: {d.model_shippable}")
    typer.echo(d.reason)


@forecast_app.command("prospective")
def forecast_prospective(commodities: str = "", market: str = "Azadpur") -> None:
    """Post tomorrow's call for a basket to the public prospective log (append-only)."""
    from vervana.db.engine import session_scope
    from vervana.digest import DEFAULT_BASKET
    from vervana.forecast.runner import run_prospective_basket

    basket = [c.strip() for c in commodities.split(",") if c.strip()] or DEFAULT_BASKET
    with session_scope() as session:
        recorded = run_prospective_basket(session, commodities=basket, market_name=market)
    if not recorded:
        typer.echo("no commodities had enough history (>21 days) to forecast")
        return
    for r in recorded:
        typer.echo(f"posted call: {r['commodity']} @ {market} via {r['model']} ({r['n_history']}d)")


@forecast_app.command("score")
def forecast_score() -> None:
    """Score any due prospective calls against realised prices, then show the track record."""
    import json

    from vervana.db.engine import session_scope
    from vervana.forecast.runner import prospective_summary, score_due, video_actual_lookup

    with session_scope() as session:
        n = score_due(session, video_actual_lookup(session))
        summary = prospective_summary(session)
    typer.echo(f"scored {n} due call(s)")
    typer.echo(
        json.dumps(
            {k: summary[k] for k in ("n_calls", "n_scored", "mae_rupees", "interval_hit_rate")},
            indent=2,
        )
    )


@ingest_app.command("invoices-csv")
def ingest_invoices_csv(path: Path) -> None:
    """Import trader invoices — the M5 ground-truth reference (upgrades the study to real)."""
    from vervana.analytics.groundtruth import import_invoices_csv
    from vervana.db.engine import session_scope

    with session_scope() as session:
        res = import_invoices_csv(session, path)
    typer.echo(f"invoices added={res['added']} rejected={res['rejected']}")


# ---------------------------------------------------------------------------
# groundtruth (M5)
# ---------------------------------------------------------------------------
groundtruth_app = typer.Typer(help="Ground-truth study (M5, R3/R4).", no_args_is_help=True)
app.add_typer(groundtruth_app, name="groundtruth")


@groundtruth_app.command("infer-units")
def groundtruth_infer_units() -> None:
    """Show the inferred per-commodity unit (kg vs quintal) for the video corpus."""
    from vervana.analytics.unit_inference import format_units, infer_units
    from vervana.db.engine import session_scope

    with session_scope() as session:
        typer.echo(format_units(infer_units(session)))


@groundtruth_app.command("report")
def groundtruth_report() -> None:
    """Run the ground-truth study (real if invoices exist, else interim video-vs-Agmarknet)."""
    from vervana.analytics.groundtruth import format_report, run_study
    from vervana.db.engine import session_scope

    with session_scope() as session:
        typer.echo(format_report(run_study(session)))


# ---------------------------------------------------------------------------
# intelligence (M9)
# ---------------------------------------------------------------------------
intelligence_app = typer.Typer(
    help="Upstream-signal intelligence (horizons, signal-to-impact outlooks).",
    no_args_is_help=True,
)
app.add_typer(intelligence_app, name="intelligence")


@intelligence_app.command("horizons")
def intelligence_horizons() -> None:
    """Show the honest forecast horizon for every profiled commodity."""
    from vervana.intelligence.crops import forecast_horizon, load_profiles

    for profile in load_profiles().values():
        h = forecast_horizon(profile)
        typer.echo(f"{h.commodity:<14} {h.label:<12} {h.basis}")


@intelligence_app.command("outlook")
def intelligence_outlook(
    commodity: str,
    save: bool = typer.Option(False, help="Persist the report (append-only audit log)."),
    observed_only: bool = typer.Option(
        False, help="Exclude simulated fixture inputs (shows what live feeds alone can say)."
    ),
) -> None:
    """Build the signal-to-impact outlook for a commodity (e.g. Sugarcane)."""
    from vervana.db.engine import session_scope
    from vervana.intelligence import build_report, format_report, save_record

    with session_scope() as session:
        report = build_report(session, commodity, include_simulated=not observed_only)
        typer.echo(format_report(report))
        if save:
            rec_id = save_record(session, report)
            typer.echo(f"\nstored as intelligence_report#{rec_id} (append-only)")


signals_app = typer.Typer(help="Upstream signal feeds.", no_args_is_help=True)
intelligence_app.add_typer(signals_app, name="signals")


@signals_app.command("import-csv")
def signals_import_csv(path: Path) -> None:
    """Import OBSERVED upstream signals (source required) into the context store."""
    from vervana.db.engine import session_scope
    from vervana.intelligence.signals import import_signals_csv

    with session_scope() as session:
        res = import_signals_csv(session, path)
    typer.echo(f"added={res['added']} rejected={res['rejected']}")
    for reason, count in sorted(res["reasons"].items(), key=lambda kv: -kv[1]):
        typer.echo(f"  rejected [{count}]: {reason}")


@signals_app.command("list")
def signals_list() -> None:
    """List the observed upstream signals currently in the context store."""
    from vervana.db.engine import session_scope
    from vervana.intelligence.signals import collect_signals

    with session_scope() as session:
        sigs = collect_signals(session)
    if not sigs:
        typer.echo("(no observed upstream signals - import with signals import-csv)")
        return
    for s in sigs:
        typer.echo(s.describe())


@app.command()
def digest(commodities: str = "") -> None:
    """Print the HoReCa procurement digest (wholesale vs quick-commerce retail spread)."""
    from vervana.db.engine import session_scope
    from vervana.digest import build_digest

    basket = [c.strip() for c in commodities.split(",") if c.strip()] or None
    with session_scope() as session:
        typer.echo(build_digest(session, basket))


@app.command()
def export(out: Path, commodity: str = "", market: str = "") -> None:
    """Export price history to a CSV file."""
    import csv as _csv

    from sqlalchemy import select

    from vervana.db.engine import session_scope
    from vervana.models.entities import Commodity, Market
    from vervana.models.observations import PriceObservation

    with session_scope() as session, Path(out).open("w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(
            [
                "id",
                "commodity",
                "market",
                "source_class",
                "canonical_rupees_per_kg",
                "price_low_paise",
                "price_high_paise",
                "unit_raw",
                "observed_at",
                "source_url",
            ]
        )
        stmt = (
            select(PriceObservation, Commodity.canonical_name, Market.canonical_name)
            .join(Commodity, Commodity.id == PriceObservation.commodity_id)
            .join(Market, Market.id == PriceObservation.market_id)
            .order_by(PriceObservation.observed_at)
        )
        if commodity:
            stmt = stmt.where(Commodity.canonical_name == commodity)
        if market:
            stmt = stmt.where(Market.canonical_name == market)
        n = 0
        for o, cname, mname in session.execute(stmt):
            canon = (
                ""
                if o.canonical_price_paise_per_kg is None
                else o.canonical_price_paise_per_kg / 100
            )
            w.writerow(
                [
                    o.id,
                    cname,
                    mname,
                    o.source_class.value,
                    canon,
                    o.price_low_paise,
                    o.price_high_paise,
                    o.unit_raw,
                    o.observed_at.isoformat(),
                    o.source_url,
                ]
            )
            n += 1
    typer.echo(f"exported {n} rows to {out}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the Vervana web platform (dashboard + API)."""
    import uvicorn

    uvicorn.run("vervana.web.app:app", host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    app()
