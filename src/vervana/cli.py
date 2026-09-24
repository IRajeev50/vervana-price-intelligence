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


def _run_migrations(revision: str = "head") -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(cfg, revision)


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Run Alembic migrations up to REVISION (default head)."""
    _run_migrations(revision)
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
    """Fetch live Agmarknet 2.0 data (public api.agmarknet.gov.in, no key) and ingest it."""
    from vervana.connectors.agmarknet import AgmarknetConnector
    from vervana.db.engine import session_scope

    connector = AgmarknetConnector()
    if not connector.enabled():
        typer.echo(f"connector '{connector.name}' is disabled via config; nothing to do")
        return
    typer.echo(
        f"fetching live Agmarknet 2.0 data (state={state}, up to {max_records} records); "
        "the Agmarknet API can be slow, this may take a few minutes..."
    )
    try:
        with session_scope() as session:
            run, result = connector.run(
                session, mode=mode, filters={"State": state}, max_records=max_records
            )
    except Exception as exc:
        # The run's own session was rolled back; record the failure in a fresh
        # transaction so `ingest history` shows it instead of a silent gap.
        with session_scope() as session:
            failed = connector.record_failure(session, mode=mode, exc=exc)
        typer.echo(f"ingest_run#{failed.id} failed: {type(exc).__name__}: {exc}", err=True)
        typer.echo(
            "no data was saved for this run; retry the same command in a few minutes",
            err=True,
        )
        raise typer.Exit(1) from exc
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


# ---------------------------------------------------------------------------
# supply-side layer (M11): satellite + agromet feeds, Google ALU/AMED seam
# ---------------------------------------------------------------------------
supply_app = typer.Typer(
    help="Supply-side feeds: Sentinel-2 NDVI, IMD rainfall, Google ALU/AMED seam.",
    no_args_is_help=True,
)
app.add_typer(supply_app, name="supply")


@supply_app.command("status")
def supply_status() -> None:
    """Show every supply feed's honest state (fallback vs scaffold, configured?)."""
    from vervana.db.engine import session_scope
    from vervana.supply.feeds import collect_feed_status, observed_supply_counts

    for f in collect_feed_status(get_settings()):
        tag = "LIVE" if f.layer == "fallback" else "SCAFFOLD"
        conf = "configured" if f.configured else "not configured"
        typer.echo(f"[{tag:<8}] {f.title}")
        typer.echo(f"           state: {f.state} ({conf})")
        typer.echo(f"           emits: {f.emits}")
        typer.echo(f"           next:  {f.hint}")
    try:
        with session_scope() as session:
            counts = observed_supply_counts(session)
    except Exception:
        counts = {}
    if counts:
        typer.echo(
            "observed supply signals in store: "
            + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        )
    else:
        typer.echo("observed supply signals in store: none yet")


@supply_app.command("ndvi")
def supply_ndvi(
    zone: str = typer.Option("", help="Limit to one zone id (default: all zones)."),
    days: int = typer.Option(30, help="Window length in days (current and year-ago)."),
) -> None:
    """Fetch Sentinel-2 NDVI for the watch zones and ingest anomaly signals."""
    from datetime import timedelta

    from vervana.connectors.sentinel2 import Sentinel2NdviConnector
    from vervana.db.engine import session_scope
    from vervana.supply.zones import load_zones
    from vervana.time import now_utc

    zones = load_zones()
    if zone:
        zones = [z for z in zones if z.zone == zone]
        if not zones:
            typer.echo(f"unknown zone '{zone}' - see data/config/supply_zones.csv", err=True)
            raise typer.Exit(code=1)
    today = now_utc().date()
    current_from, current_to = today - timedelta(days=days), today
    baseline_from = current_from.replace(year=current_from.year - 1)
    baseline_to = current_to.replace(year=current_to.year - 1)

    conn = Sentinel2NdviConnector()
    try:
        records = conn.fetch_raw(
            zones=zones,
            current_from=current_from,
            current_to=current_to,
            baseline_from=baseline_from,
            baseline_to=baseline_to,
        )
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    with session_scope() as session:
        run, result = conn.ingest_with_run(session, records, mode="api")
        typer.echo(
            f"ingest_run#{run.id}: rows_in={result.rows_in} "
            f"accepted={result.accepted} rejected={result.rejected}"
        )
        for reason, count in sorted(result.reason_counts.items(), key=lambda kv: -kv[1]):
            typer.echo(f"  rejected [{count}]: {reason}")


@supply_app.command("rainfall-fetch")
def supply_rainfall_fetch(
    zone: str = typer.Option("", help="Limit to one zone id (default: all zones)."),
) -> None:
    """Fetch IMD's all-India district PDF and ingest watch-zone rainfall signals.

    Downloads the Hydromet Division districtwise bulletin, parses each watch-zone
    district's seasonal cumulative % departure, and ingests them as observed
    rainfall_deficit_pct signals - the automated twin of `rainfall-import`. The
    observation date comes from the PDF's own period line; districts the PDF does
    not yield are reported, never invented.
    """
    from vervana.connectors.imd import ImdRainfallConnector
    from vervana.db.engine import session_scope
    from vervana.supply.imd_fetch import build_records
    from vervana.supply.zones import load_zones

    zones = load_zones()
    if zone:
        zones = [z for z in zones if z.zone == zone]
        if not zones:
            typer.echo(f"unknown zone '{zone}' - see data/config/supply_zones.csv", err=True)
            raise typer.Exit(code=1)
    try:
        records, missing, as_of = build_records(zones, settings=get_settings())
    except Exception as exc:  # network / parse failure: say so, ingest nothing
        typer.echo(f"rainfall-fetch failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(
        f"IMD bulletin as of: {as_of or 'unknown'} · parsed {len(records)} watch-zone districts"
    )
    if not records:
        typer.echo("no watch-zone districts parsed from the PDF - nothing ingested", err=True)
        if missing:
            typer.echo(f"  missing: {', '.join(missing)}")
        raise typer.Exit(code=1)
    with session_scope() as session:
        run, result = ImdRainfallConnector().ingest_with_run(session, records, mode="fetch")
    typer.echo(
        f"ingest_run#{run.id}: rows_in={result.rows_in} "
        f"accepted={result.accepted} rejected={result.rejected}"
    )
    if missing:
        typer.echo(f"  not found in PDF (unchanged, not invented): {', '.join(missing)}")


@supply_app.command("rainfall-import")
def supply_rainfall_import(path: Path) -> None:
    """Import IMD district rainfall (CSV) as observed rainfall_deficit_pct signals."""
    import csv as _csv

    from vervana.connectors.imd import ImdRainfallConnector
    from vervana.db.engine import session_scope

    with Path(path).open(encoding="utf-8") as fh:
        records = list(_csv.DictReader(fh))
    with session_scope() as session:
        run, result = ImdRainfallConnector().ingest_with_run(session, records, mode="csv")
        typer.echo(
            f"ingest_run#{run.id}: rows_in={result.rows_in} "
            f"accepted={result.accepted} rejected={result.rejected}"
        )
    for reason, count in sorted(result.reason_counts.items(), key=lambda kv: -kv[1]):
        typer.echo(f"  rejected [{count}]: {reason}")


@supply_app.command("alu")
def supply_alu() -> None:
    """Google ALU seam status (SCAFFOLD - partner access pending)."""
    from vervana.supply.alu import AluClient

    s = AluClient(get_settings()).status()
    typer.echo(f"{s.title} [{s.state}]")
    typer.echo(f"will emit: {s.emits}")
    typer.echo(f"next: {s.hint}")
    typer.echo(f"docs: {s.docs_url}")
    typer.echo("nothing is fetched and nothing is faked until access is configured")


@supply_app.command("amed")
def supply_amed() -> None:
    """Google AMED seam status (SCAFFOLD - partner access pending)."""
    from vervana.supply.amed import AmedClient

    s = AmedClient(get_settings()).status()
    typer.echo(f"{s.title} [{s.state}]")
    typer.echo(f"will emit: {s.emits}")
    typer.echo(f"next: {s.hint}")
    typer.echo(f"docs: {s.docs_url}")
    typer.echo("nothing is fetched and nothing is faked until access is configured")


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


def _print_setup_steps(steps) -> bool:
    """Render the shared first-run checklist; return True when everything is done."""
    all_ok = True
    for step in steps:
        mark = "ok  " if step.ok else "TODO"
        typer.echo(f"[{mark}] {step.label}: {step.detail}")
        if not step.ok:
            all_ok = False
            typer.echo(f"       next: {step.action}")
    return all_ok


@app.command()
def setup() -> None:
    """First-run bootstrap (idempotent): create tables, seed the registry, report status.

    Safe to re-run any number of times: migrations apply only what is missing and
    the registry seed never duplicates existing rows. Seeding loads *reference*
    data only (commodity/market names); live prices still come from an ingest run.
    """
    from vervana.db.engine import session_scope
    from vervana.repository.aspirational import import_seed as import_aspirational
    from vervana.repository.registry import seed_registry
    from vervana.setup_status import collect_setup_steps

    typer.echo("1/2  migrating database ...")
    _run_migrations()
    typer.echo("2/2  seeding registry (commodities, varieties, markets, units) ...")
    settings = get_settings()
    with session_scope() as session:
        counts = seed_registry(session, SEED_DIR)
        # Aspirational Districts are canonical reference data (the official NITI
        # list), so a fresh clone gets them here alongside the registry seed.
        adp = import_aspirational(session, SEED_DIR / "aspirational_districts.csv")
        counts["aspirational"] = adp["total_in_file"]
    for k, v in counts.items():
        typer.echo(f"     {k:12} {v}")
    typer.echo("")
    typer.echo("Setup checklist:")
    with session_scope() as session:
        steps = collect_setup_steps(session, settings)
    if _print_setup_steps(steps):
        typer.echo("all done - run: uv run vervana serve")


@app.command()
def doctor() -> None:
    """Diagnose first-run setup: what is done, what is missing, and the exact fix."""
    from vervana.db.engine import session_scope
    from vervana.setup_status import SETUP_COMMAND, collect_setup_steps

    settings = get_settings()
    typer.echo("Setup checklist:")
    try:
        with session_scope() as session:
            steps = collect_setup_steps(session, settings)
    except Exception as exc:  # DB missing/unmigrated: the checklist cannot even run
        typer.echo(f"[TODO] database: cannot read it ({exc.__class__.__name__})")
        typer.echo(f"       next: {SETUP_COMMAND}")
        raise typer.Exit(code=1) from None
    if not _print_setup_steps(steps):
        raise typer.Exit(code=1)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the Vervana web platform (dashboard + API)."""
    import uvicorn
    from sqlalchemy import func, select

    from vervana.db.engine import session_scope
    from vervana.models.entities import Commodity
    from vervana.setup_status import SETUP_COMMAND

    # Fail loudly and helpfully instead of serving 500s on an unmigrated database.
    try:
        with session_scope() as session:
            session.scalar(select(func.count()).select_from(Commodity))
    except Exception:
        typer.echo(f"database is not ready - run: {SETUP_COMMAND}", err=True)
        raise typer.Exit(code=1) from None

    uvicorn.run("vervana.web.app:app", host=host, port=port)


# ---------------------------------------------------------------------------
# crops (district production context, official DES/APY statistics)
# ---------------------------------------------------------------------------
crops_app = typer.Typer(
    help="District crop production (official DES/APY supply context).",
    no_args_is_help=True,
)
app.add_typer(crops_app, name="crops")

NATIONAL_CACHE = REPO_ROOT / "data" / "cache" / "crop_apy_national.csv"


def _download_national_apy(dest: Path) -> Path:
    """Fetch the full all-India DES/APY CSV (keyless India Data Portal download)."""
    import httpx

    from vervana.repository.crop_production import NATIONAL_APY_URL

    dest.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"downloading national APY file -> {dest}")
    with httpx.stream("GET", NATIONAL_APY_URL, follow_redirects=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=1 << 20):
                fh.write(chunk)
    typer.echo(f"downloaded {dest.stat().st_size / 1e6:,.1f} MB")
    return dest


@crops_app.command("import-apy")
def crops_import_apy(
    path: Path = REPO_ROOT / "data" / "seed" / "crop_apy_pilot_districts.csv",
    national: bool = typer.Option(
        False, "--national", help="Download and import the full all-India file (740 districts)."
    ),
) -> None:
    """Import official district crop production (idempotent; safe to re-run).

    Default imports the 3-district pilot seed. --national downloads the full
    DES/APY file (34 states/UTs, 740 districts, 1997-98 to 2022-23) from the
    India Data Portal and imports it; already-present rows are skipped, so it
    is safe to run after the pilot import. The read rollup is rebuilt at the
    end so the District insights pages pick up the new data.
    """
    from vervana.db.engine import session_scope
    from vervana.repository.crop_production import import_apy_csv, rebuild_rollup

    if national:
        path = _download_national_apy(NATIONAL_CACHE)
    with session_scope() as session:
        res = import_apy_csv(session, path)
        typer.echo(
            f"crop production rows added={res['added']} skipped={res['skipped']} rejected={res['rejected']}"
        )
        for reason, count in sorted(res["reasons"].items(), key=lambda kv: -kv[1]):
            typer.echo(f"  rejected [{count}]: {reason}")
        n = rebuild_rollup(session)
    typer.echo(f"rollup rebuilt: {n} district-year-crop rows")


@crops_app.command("refresh-rollups")
def crops_refresh_rollups() -> None:
    """Rebuild the derived district-year-crop read model from the raw rows."""
    from vervana.db.engine import session_scope
    from vervana.repository.crop_production import rebuild_rollup

    with session_scope() as session:
        n = rebuild_rollup(session)
    typer.echo(f"rollup rebuilt: {n} district-year-crop rows")


@crops_app.command("summary")
def crops_summary(state: str = "") -> None:
    """Latest-year production per district (annual row preferred; never double-counted)."""
    from vervana.db.engine import session_scope
    from vervana.repository.crop_production import district_directory

    with session_scope() as session:
        data = district_directory(session, state=state)
        if not data["rows"]:
            typer.echo("no crop production data - run: uv run vervana crops import-apy")
            return
        for d in data["rows"]:
            typer.echo(f"{d['district']} ({d['state']}) {d['latest_year']}: {d['total']:,.0f} t")
            typer.echo(f"    top crops: {', '.join(d['top_crops'])}")


aspirational_app = typer.Typer(
    help="NITI Aayog Aspirational Districts (programme membership + supply overlay).",
    no_args_is_help=True,
)
app.add_typer(aspirational_app, name="aspirational")


@aspirational_app.command("import")
def aspirational_import(
    path: Path = SEED_DIR / "aspirational_districts.csv",
) -> None:
    """Import the official NITI list of 112 Aspirational Districts (idempotent)."""
    from vervana.db.engine import session_scope
    from vervana.repository.aspirational import import_seed

    with session_scope() as session:
        res = import_seed(session, path)
    typer.echo(
        f"aspirational districts: added={res['added']} updated={res['updated']} "
        f"({res['total_in_file']} in file)"
    )


@aspirational_app.command("summary")
def aspirational_summary() -> None:
    """Headline counts, by-state distribution, and overlap with our crop data."""
    from vervana.db.engine import session_scope
    from vervana.repository.aspirational import overview

    with session_scope() as session:
        ov = overview(session)
    if ov["total"] == 0:
        typer.echo("no data - run: uv run vervana aspirational import")
        return
    typer.echo(f"{ov['total']} districts across {ov['states']} states/UTs")
    if ov["have_production_layer"]:
        typer.echo(f"crop-production data held for {ov['covered']} of them")
    for row in ov["by_state"]:
        typer.echo(f"  {row['state']:<24} {row['count']}")


sourcing_app = typer.Typer(
    help="Sourcing directory: import official supplier organisations.",
    no_args_is_help=True,
)
app.add_typer(sourcing_app, name="sourcing")


@sourcing_app.command("import-cdb-coconut")
def sourcing_import_cdb_coconut() -> None:
    """Import the official Coconut Development Board producer-company directory.

    Fetches the CDB Coconut Producer Companies contact PDF, parses one record per
    company (name, state, a primary contact), and upserts them as Coconut
    suppliers - an official, consent-clean directory, never scraped trader data.
    """
    from vervana.db.engine import session_scope
    from vervana.repository.sourcing import import_suppliers
    from vervana.supply.cdb import build_supplier_records

    try:
        records, url = build_supplier_records()
    except Exception as exc:  # network / parse failure: ingest nothing
        typer.echo(f"cdb-coconut import failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    with_phone = sum(1 for r in records if r.get("phone"))
    with session_scope() as session:
        res = import_suppliers(session, records)
    typer.echo(
        f"CDB coconut suppliers: parsed={len(records)} "
        f"(with phone={with_phone}) added={res['added']} updated={res['updated']}"
    )
    typer.echo(f"source: {url}")


@sourcing_app.command("import-spices-fpo")
def sourcing_import_spices_fpo() -> None:
    """Import the official Spices Board FPO/FPC directory (pepper, turmeric, etc.).

    One producer organisation that grows several spices becomes one supplier row
    per priced commodity (Pepper->Black pepper, Turmeric, Ginger, Chilli->Dry
    Chillies), so each shows under its commodity on the sourcing board.
    """
    from vervana.db.engine import session_scope
    from vervana.repository.sourcing import import_suppliers
    from vervana.supply.spices_fpo import build_supplier_records

    try:
        records, url = build_supplier_records()
    except Exception as exc:
        typer.echo(f"spices-fpo import failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    with_phone = sum(1 for r in records if r.get("phone"))
    with session_scope() as session:
        res = import_suppliers(session, records)
    typer.echo(
        f"Spices Board FPO suppliers: rows={len(records)} "
        f"(with phone={with_phone}) added={res['added']} updated={res['updated']}"
    )
    typer.echo(f"source: {url}")


if __name__ == "__main__":  # pragma: no cover
    app()
