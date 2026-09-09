# ADR 0001 — Technology stack

- **Status:** PROPOSED — blocks all application code until the founder approves (Gate 2).
- **Date:** 2026-09-10
- **Deciders:** founder (approval), lead engineer (proposal)
- **Supersedes:** —

## Context

The constraints (from [`BUILD_PROMPT.md`](../BUILD_PROMPT.md) Gate 2 and Part 7) are
unusually decisive and mostly point the same way:

1. **Non-technical founders; a junior Indian developer must be able to maintain it.**
   Boring, mainstream, well-documented tech with a deep local hiring pool beats
   anything clever.
2. **The market is small.** TAM ≈ ₹154 cr/yr; Delhi-NCR SAM ≈ ₹6.6 cr/yr; realistic
   year-one ceiling ₹20–29 lakh ARR. **Any stack whose fixed monthly cost exceeds
   ₹25,000 is disqualified by arithmetic.** The competitor (MandiBhav) sells from
   ₹99/mo and the underlying Agmarknet data is free.
3. **The workload is daily-batch,** not high-concurrency serving: time-series ingest,
   entity resolution, small-scale model training, and a low-traffic API/dashboard/
   WhatsApp digest. User count barely moves infrastructure.
4. **Text is Devanagari + Hinglish transliteration.** The stack must have first-class
   Indic NLP / transliteration / fuzzy-matching libraries.
5. **Deployment in India; data residency preferred.**
6. **Provenance is enforced in the database** (Part 3): source-class guard, ranges not
   collapsed, provenance-required columns, append-only with `supersedes_id`. This is a
   *relational-constraints* problem, not a document-store problem.

## Decision (proposed)

A **single-language, single-box, batch-first** stack:

| Layer | Choice |
|---|---|
| Language | **Python 3.12** |
| Datastore (prod) | **PostgreSQL 16** (self-hosted in Docker, Indian region) |
| Datastore (dev/tests) | **SQLite** for unit tests; Postgres via Docker Compose for integration |
| Migrations | **Alembic** |
| DB access | **SQLAlchemy 2.x** (Core + light ORM), with a hand-written repository layer that enforces the source-class guard |
| API | **FastAPI** + **Pydantic v2** |
| Dashboard | **Server-rendered Jinja2 templates + HTMX** (no SPA) |
| CLI / batch entrypoints | **Typer** |
| Scheduling | **system `cron`** on the box, invoking Typer commands; ingest-run table records every run |
| Time-series / stats | **statsmodels** (SARIMA), **Prophet** (optional), **pandas**/**numpy** |
| Gradient boosting | **scikit-learn HistGradientBoosting** first; LightGBM only if justified |
| Fuzzy / transliteration | **rapidfuzz** + **indic-transliteration** (+ `indic-nlp-library`); a multilingual sentence-embedding approach evaluated as the *second* M1 method, computed in batch and kept optional |
| Config / secrets | **pydantic-settings**, values from environment; `.env.example` committed, `.env` never |
| Logging | **structlog** (JSON) |
| Packaging / deps | **uv** (fast, reproducible) with `pyproject.toml` + lockfile |
| Lint / format / hooks | **ruff** (lint+format) + **pre-commit** |
| Container / local dev | **Docker Compose** (app + postgres) |
| CI | **GitHub Actions** (lint, tests offline, migration check) |
| Hosting | **One VPS in an Indian region** (e.g. AWS/GCP Mumbai, DigitalOcean Bangalore, or an Indian provider), Docker Compose, nightly `pg_dump` to Indian object storage |

**One language, one box, cron for scheduling, Postgres for truth.** Nothing in the
workload justifies more, and everything in the constraints punishes more.

## Options considered and why the rest were rejected

### Language
- **Python (chosen).** The time-series, stats, ML, fuzzy-matching and Indic-NLP
  ecosystems live here; the junior-developer hiring pool in India is deepest here for
  data work. One language covers ingest, models, API and dashboard.
- **Node.js / TypeScript — rejected.** Strong for the API/dashboard, but the
  statistics/forecasting and Indic-NLP ecosystems are weak, which would force a *second*
  language for the models — exactly the maintainability cost we must avoid. The core
  work is data/stats, not web serving.
- **Go or JVM (Kotlin/Java) — rejected.** Excellent concurrent serving we do not need
  for a daily-batch, low-traffic product; thin statistics/ML ecosystem; smaller pool of
  *junior* Indian devs who could own the modelling code. Overkill against the workload.

### Datastore
- **PostgreSQL (chosen).** The data model is a set of relational invariants that must be
  enforced *in the database* (Part 3). Postgres gives CHECK constraints, enums, foreign
  keys, partial/unique indexes, `JSONB` for raw payloads, and a clean upgrade path to
  TimescaleDB later without a migration. It is the datastore a junior dev is most likely
  to already know.
- **SQLite only — rejected for prod, kept for tests.** Perfectly adequate at 10 users and
  wonderful for offline unit tests, but weaker concurrent writes, no real enum types, and
  a constraint/JSON story that would make the provenance guards harder to enforce
  faithfully. Using it for tests keeps `make test` fast and network-free (Part 1.5); using
  Postgres for prod keeps the guarantees real.
- **A document/NoSQL store (Mongo/Firestore) — rejected.** The entire point is
  relational constraints that block bad aggregation. A schema-flexible store makes the
  one thing we must guarantee (provenance, no cross-class averaging) *harder*, not easier.
- **A dedicated TSDB (InfluxDB) now — rejected as premature.** The heavy relational work
  (entity registry, aliases, unit conventions, provenance) dominates; time-series volume
  is tiny (~90 obs/series). If serving-side time-series ever grows, **TimescaleDB is a
  Postgres extension** we can enable in place. Adopting a separate TSDB now adds a system
  a junior dev must learn for no benefit.

### Serving / dashboard
- **FastAPI + Jinja/HTMX (chosen).** Same language as everything else; automatic API
  docs; Pydantic validation aligns with the provenance discipline; server-rendered pages
  make "every number links to its evidence row" trivial and need no build toolchain.
- **React/Next SPA — rejected.** A second language and a build/deploy toolchain a junior
  dev must also own, for a *minimal* internal-facing dashboard. Not worth the complexity
  or the cognitive load.
- **Streamlit — rejected as the primary UI (may reuse internally).** Fast to prototype,
  but awkward to make each price a stable, linkable evidence URL and to run the same app
  as a public API. Fine as an internal analyst view for the coverage/ground-truth reports
  if useful; not the product surface.

### Orchestration / scheduling
- **cron + Typer CLI + ingest-run table (chosen).** The workload is "run these jobs once
  a day and record what happened." Cron is on every Linux box, costs nothing, and a
  junior dev can read a crontab. Idempotent CLI commands + an ingest-run metadata table
  give us observability without a framework.
- **Airflow / Prefect / Dagster — rejected.** Real fixed cost (a scheduler + DB +
  worker, or a paid cloud tier), real operational surface, and a steep learning curve —
  all to schedule a handful of daily jobs. Disqualified on cost *and* maintainability.

### Hosting
- **Single Indian-region VPS + Docker Compose (chosen).** Cheapest path that satisfies
  India data residency, keeps Postgres and the app co-located (no egress, no managed-DB
  fee), and is documentable in a `RUNBOOK.md` a junior can follow. Nightly `pg_dump` to
  Indian object storage covers backups.
- **Managed PaaS (Render / Railway / Fly.io) — rejected as default.** Convenient, but
  pricier at steady state and **data residency in India is not guaranteed** on the cheap
  tiers. Residency is a stated preference we can satisfy for less with a VPS.
- **Serverless (Lambda/Cloud Functions) — rejected.** A poor fit for a stateful,
  daily-batch, Postgres-backed workload; cold starts and execution limits fight the
  batch/model jobs; and it complicates the "one box a junior can SSH into" model.
- **Managed Postgres (RDS / Supabase / Neon) — rejected for now.** At 10–1,000 users the
  self-hosted Postgres-in-Docker option is materially cheaper and keeps residency simple.
  Supabase's Mumbai region is a viable future option if ops burden becomes a problem;
  noted, not adopted.

## Monthly running-cost estimate (fixed software/infra only)

All figures are **fixed** infrastructure at rest. They exclude the two cost stories that
do *not* belong to the software ceiling and are tracked separately in
[`RUNNING_COSTS.md`](../RUNNING_COSTS.md): **variable messaging/compute** (WhatsApp
Business API per-conversation, any ASR/LLM/embedding API calls) and **R12 observer
payroll** (opex that scales with mandi count and dwarfs everything here).

| Users | Infra | Est. ₹/mo (fixed) | Notes |
|---|---|---|---|
| **10** | 1× 2 GB VPS (India), domain, backups | **₹1,500 – 2,000** | Daily batch barely loads the box; could even run Postgres + app + cron on one 2 GB instance. |
| **100** | 1× 4 GB VPS (India), object storage for raw payloads, backups | **₹3,000 – 4,000** | Still one box. Object storage for archived raw API/transcript payloads. |
| **1,000** | 1× 8 GB VPS (India), CDN for dashboard/static, backups | **₹6,000 – 8,000** | Serving 1,000 users of a daily price API/digest is trivial; the bump is headroom for model training + raw-payload storage, not concurrency. |

**Conclusion on the ceiling:** even at 1,000 users, fixed software cost (~₹6–8k/mo) sits
comfortably under the ₹25,000/mo disqualification line — roughly a **3× margin**. The
binding cost constraint on the *business* is not this stack; it is observer payroll (R12)
and per-message WhatsApp fees, both variable and both tracked outside this ceiling.

**Watch-items that could threaten the ceiling** (flagged, not incurred yet):
- A multilingual **sentence-embedding** model for entity matching pulls in `torch`
  (~2 GB RAM, heavier CPU). Mitigation: compute embeddings in nightly batch, cache them,
  or use a small model / a metered embedding API. Evaluated in M1; kept optional so the
  rapidfuzz+transliteration path can stand alone.
- **ASR** for field-observer voice notes (M7): use a metered API or a small local model
  in batch; it is variable cost, not fixed, and belongs in `RUNNING_COSTS.md`.
- **Managed-service creep** (jumping to RDS/Supabase/PaaS for convenience) is the most
  likely way this ceiling gets breached; the ADR resists it deliberately.

## Consequences

- **Positive:** one language end-to-end; one box a junior can operate from a runbook;
  database-enforced provenance; free scheduling; India residency satisfied; ~3× cost
  headroom; clean, non-lock-in upgrade paths (TimescaleDB in place, managed Postgres or
  PaaS later if ops burden grows).
- **Negative / accepted trade-offs:** a single VPS is a single point of failure (mitigated
  by nightly off-box backups + a documented restore in `RUNBOOK.md`, not by expensive HA
  we cannot justify); self-hosting Postgres is a small ops burden (mitigated by Docker
  Compose + backups); server-rendered dashboard is less "appy" than an SPA (intended — the
  product surface is data + evidence links + WhatsApp, not a rich web app).
- **Data-residency caveats to record in `OPEN_QUESTIONS.md`:** the **WhatsApp Business
  API (Meta)** and any **cloud ASR/LLM/embedding** provider may process data outside
  India; that is a per-integration decision to make when those features land, not now.

## What I need from the founder

**Approve, amend, or reject this ADR.** No application code will be written until it is
approved (Gate 2). Specific points worth an explicit nod:
1. Python + Postgres + FastAPI + single Indian VPS + cron — acceptable?
2. Comfortable self-hosting Postgres in Docker rather than paying for managed Postgres at
   this scale?
3. Any existing cloud account/region preference (AWS Mumbai vs GCP Mumbai vs an Indian
   provider) I should target in the runbook?
