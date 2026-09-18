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

**Early build.** Foundations milestone (M0). No data collection is running yet. The
YouTube transcript source is **on hold pending a legal opinion** and is deliberately not
built. See [`docs/BUILD_PROMPT.md`](docs/BUILD_PROMPT.md) for the full plan and
[`docs/milestones/`](docs/milestones/) for milestone-by-milestone progress.

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

To fill it with live national data (needs your data.gov.in key in `.env`), the daily
capture runs automatically (see `docs/RUNBOOK.md`), or do it once by hand:

```bash
bash scripts/daily_capture.sh                                   # pull today's snapshot
uv run vervana registry bootstrap data/raw/agmarknet/snapshot_*.json   # learn its names
uv run vervana ingest agmarknet-file data/raw/agmarknet/snapshot_*.json # ingest prices
```

Or fetch a single state straight from the API (also needs the key in `.env`):

```bash
uv run vervana ingest agmarknet --state Delhi --max-records 100
uv run vervana ingest history   # every run shows here, including failures
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

data.gov.in is often slow (a page can take over a minute), so the connector uses a
120s timeout and retries slow/failed responses a few times before giving up. A failed
capture saves nothing but is recorded in `ingest history`; just rerun the same
command — re-ingesting the same rows is safe (duplicates are rejected, not doubled).
To tune the budget, set `VERVANA_AGMARKNET_TIMEOUT_SECONDS` /
`VERVANA_AGMARKNET_MAX_RETRIES` in `.env`.

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
- [`docs/SUPPLY.md`](docs/SUPPLY.md) — the M11 supply-side layer: Sentinel-2 NDVI + IMD rainfall feeds (live), and the Google ALU/AMED connector seam (scaffold, partner access pending).
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — what to do when something breaks.

## Licensing & attribution (applies once Agmarknet data is displayed)

Agmarknet price data is published under the **Government Open Data License – India
(GODL-India)** and carries the **DMI accuracy disclaimer**; both must be shown wherever
that data appears. See [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md).
