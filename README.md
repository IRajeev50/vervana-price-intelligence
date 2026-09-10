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
uv run vervana db upgrade         # create the database
uv run vervana registry seed      # load the Delhi F&V starter registry
uv run vervana serve              # start the web app at http://127.0.0.1:8000
```

Then open **http://127.0.0.1:8000**. Pages: **Dashboard** (totals + R5 status),
**Prices** (browse/filter, every row links to its evidence), **Coverage (R5)** (the
Delhi coverage experiment + daily probe), **Review** (approve alias matches), **Ingest**
(capture history).

To fill it with live national data (needs your data.gov.in key in `.env`), the daily
capture runs automatically (see `docs/RUNBOOK.md`), or do it once by hand:

```bash
bash scripts/daily_capture.sh                                   # pull today's snapshot
uv run vervana registry bootstrap data/raw/agmarknet/snapshot_*.json   # learn its names
uv run vervana ingest agmarknet-file data/raw/agmarknet/snapshot_*.json # ingest prices
```

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
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — what to do when something breaks.

## Licensing & attribution (applies once Agmarknet data is displayed)

Agmarknet price data is published under the **Government Open Data License – India
(GODL-India)** and carries the **DMI accuracy disclaimer**; both must be shown wherever
that data appears. See [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md).
