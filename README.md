# Vervana — Price Intelligence & Procurement Platform

A price-intelligence platform for Indian fresh produce, starting with **Delhi mandis**.
It collects produce prices from public and field sources, resolves the messy naming of
Indian commodities, and serves trustworthy, **fully-traceable** prices — every number
links back to the evidence it came from.

> **Guiding principle:** the product is *data you can trust*. So the system is built to
> make lying hard — it never averages a supermarket price with a wholesale quote, never
> collapses a price range into a fake single number, and never stores a price it cannot
> trace to a source. If we do not know something, it says so.

## Status

**Active build, data flowing.** The platform captures national Agmarknet prices, resolves
the messy naming of Indian commodities, and serves fully-traceable prices, forecasts, and
advisory intelligence. The YouTube transcript source remains **on hold pending a legal
opinion** and is deliberately not built. See [`docs/BUILD_PROMPT.md`](docs/BUILD_PROMPT.md)
for the full plan and [`docs/milestones/`](docs/milestones/) for milestone-by-milestone
progress.

Two honesty guardrails shape what "done" means here:

- **Nothing ships off a price-edge it hasn't earned.** A forecast band must beat an
  anchor + seasonal-naive baseline on a per-commodity walk-forward backtest — the *kill
  gate*. Today **0 of 45** commodities clear it, so every forward price is a labelled
  baseline and [The Book](docs/milestones/M17-done.md) stays advisory. That is the honest
  state, not a bug.
- **Partner feeds that aren't granted fetch nothing and fake nothing.** WeatherNext and
  Flood Hub are built up to the access boundary and wait there; absence of data is shown
  as "access pending", never as "no risk".

### Milestones

| Milestone | What it adds | State |
|---|---|---|
| M0–M12 | Foundations: capture, registry, coverage, entity matching, intelligence chain, crop production, forecast band + kill gate | operational |
| [M13](docs/milestones/M13-done.md) · WeatherNext seam | forward weather feed (BigQuery percentiles) | scaffold — access pending |
| [M15](docs/milestones/M15-done.md) · Flood Hub seam | riverine flood risk overlay (origin belts) | scaffold — access pending |
| [M16](docs/milestones/M16-audit.md) · Audit | full-repo gap analysis | done |
| [M17](docs/milestones/M17-done.md) · The Book | inventory lots + carrying cost + HOLD/RELEASE/WAIT/REROUTE | operational (advisory) |
| [M18](docs/milestones/M18-done.md) · Capsicum & Onion | evidence-cited sourcing belts + market coords (REROUTE live) | operational |
| [M19a](docs/milestones/M19-done.md) · Flood destination flag | Book riverine flood-driven REROUTE (access-free slice) | operational |
| [Arrivals capture](docs/milestones/arrivals-capture-done.md) | store mandi arrivals (tonnes) going forward | operational |
| [M20a](docs/milestones/M20a-done.md) · Weather belt→mandi link | dormant weather-feature builder (access-free slice) | operational |
| [M19b](docs/milestones/M19-plan.md) · Flood Hub go-live | live gauge pull | **blocked on access** (API key) |
| [M20b](docs/milestones/M20-plan.md) · WeatherNext go-live | live BigQuery pull + kill-gate re-run | **blocked on access** (GCP credentials) |

The two go-lives (M19b, M20b) need operator-supplied credentials and nothing else; each
`*-plan.md` says exactly what to provide.

## How to run it (for developers)

You need [`uv`](https://docs.astral.sh/uv/) installed. It manages the right Python
version (3.12) for you — you do **not** need to install Python separately.

```bash
uv sync            # or: make setup   — create the environment and install everything
make test          # run the test suite (works fully offline)
make lint          # check code style
make risks         # regenerate the risk register from the code
uv run vervana healthcheck   # prove the app loads and is configured correctly
```

### Run the platform (web dashboard + API)

```bash
uv run vervana setup              # first run: create the database + seed the registry (idempotent)
uv run vervana serve              # start the web app at http://127.0.0.1:8000
```

`setup` is safe to re-run: migrations apply only what is missing and the seed never
duplicates rows. It loads *reference* data (commodity/market names) only - live
prices appear after a successful capture below. If the dashboard looks empty,
`uv run vervana doctor` prints a checklist of what is done, what is missing, and
the exact next command; the dashboard shows the same checklist until setup is
complete.

Then open **http://127.0.0.1:8000**. Pages: **Dashboard** (totals + R5 status),
**Prices** (browse/filter, every row links to its evidence), **Coverage (R5)** (the
Delhi coverage experiment + daily probe), **Intelligence** (crop portfolio +
signal-to-impact outlooks), **Outlook calendar** (every saved outlook by the date
it was made), **Review** (approve alias matches), **Ingest** (capture history).
The UI runs on the design system in [`docs/UI.md`](docs/UI.md) (M10).

To fill it with live national data, the daily capture runs automatically (see
`docs/RUNBOOK.md`), or do it once by hand. The Agmarknet 2.0 public API
(`api.agmarknet.gov.in`) is **keyless** — no `.env` entry is required:

```bash
uv run vervana ingest agmarknet --state Delhi --max-records 100   # keyless live pull + ingest
uv run vervana ingest history   # every run shows here, including failures
```

`scripts/daily_capture.sh` wraps the same keyless call (`vervana ingest agmarknet
--state Delhi`) with a schema upgrade, a registry seed, and a wait-for-network
guard, so GitHub Actions / launchd can run it unattended.

To replay a locally-saved payload offline (no network) — or to learn the registry
names from one — ingest or bootstrap the saved JSON directly:

```bash
uv run vervana registry bootstrap data/raw/agmarknet/snapshot_*.json    # learn official names
uv run vervana ingest agmarknet-file data/raw/agmarknet/snapshot_*.json  # ingest saved prices
```

Upstream supply signals (M11) have their own feeds: Sentinel-2 NDVI and IMD
district rainfall work today; the Google ALU/AMED connector is a labelled
scaffold until partner access is approved (it fetches nothing and fakes
nothing). Status and setup:

```bash
uv run vervana supply status                # every feed: layer, state, next step
uv run vervana supply ndvi                  # Sentinel-2 anomalies (needs free CDSE creds)
uv run vervana supply rainfall-import my.csv  # IMD district rainfall
```

District crop production (official DES/APY statistics, Ministry of Agriculture) is
the physical supply layer under the price layer - **Research → District insights**
lists every district with key figures and taps through to a full per-district card.
The full all-India file (34 states/UTs, 740 districts, 1997-98 to 2022-23, ~455k
rows) downloads keyless from the India Data Portal; NITI for States aggregates the
same source and exposes no usable public API:

```bash
uv run vervana crops import-apy --national   # all-India (downloads ~56 MB once)
uv run vervana crops import-apy              # 3-district pilot seed only
uv run vervana crops summary                 # latest-year totals per district
uv run vervana crops refresh-rollups         # rebuild the read model by hand
```

Raw rows are stored exactly as published; every total is computed from them via a
derived rollup, preferring the official annual "Total" row and never adding Total +
seasonal rows together. DES publishes coconut in nuts, not tonnes - coconut is
labelled "nuts" and never enters tonne totals.

The Agmarknet 2.0 API (`api.agmarknet.gov.in`) can be slow (a report can take over a
minute), so the connector uses a 120s timeout and retries slow/failed responses a few
times before giving up. A failed capture saves nothing but is recorded in `ingest
history`; just rerun the same command — re-ingesting the same rows is safe (duplicates
are rejected, not doubled). To tune the budget, set
`VERVANA_AGMARKNET_TIMEOUT_SECONDS` / `VERVANA_AGMARKNET_MAX_RETRIES` in `.env`.

To run the local database + app together (needs Docker):

```bash
cp .env.example .env    # then fill in any secrets locally
make up                 # start Postgres + app
make down               # stop them
```

## What's in here

| Path | What it is |
|---|---|
| `src/vervana/` | The application code. |
| `tests/` | Offline tests (no network — see the build spec). |
| `scripts/` | Tooling, incl. the risk-register generator. |
| `docs/` | The plan, decisions, risk register, running costs, runbook, data dictionary. |

## Key documents

- [`docs/UNDERSTANDING.md`](docs/UNDERSTANDING.md) — plain-language read of what we're building and the honest risks.
- [`docs/adr/0001-stack.md`](docs/adr/0001-stack.md) — why this technology stack (and its running cost).
- [`docs/RISK_REGISTER.md`](docs/RISK_REGISTER.md) — the assumptions the product rests on, and their status (generated, never hand-edited).
- [`docs/RUNNING_COSTS.md`](docs/RUNNING_COSTS.md) — what it costs to run, kept honest.
- [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) — things not yet settled.
- [`docs/INTELLIGENCE.md`](docs/INTELLIGENCE.md) — the M9 upstream-signal intelligence layer: reasoning chain, honesty rules, honest horizons, sugar worked example.
- [`docs/SUPPLY.md`](docs/SUPPLY.md) — the supply-side layer: Sentinel-2 NDVI + IMD rainfall feeds (live), the Google ALU/AMED/WeatherNext/Flood Hub seams (scaffold, access pending), the evidence-cited sourcing belts + belt→mandi weather links (M18/M20a), and the riverine flood destination flag (M19a).
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — what to do when something breaks.

## Licensing & attribution (applies once Agmarknet data is displayed)

Agmarknet price data is published under the **Government Open Data License – India
(GODL-India)** and carries the **DMI accuracy disclaimer**; both must be shown wherever
that data appears. See [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md).
