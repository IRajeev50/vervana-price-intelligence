# M13 - Phase 1: WeatherNext 3 as a forward weather supply feed - PLAN

- **Status:** PLANNED (2026-11-14). No code until Rajeev's go.
- **Working gate (agreed, option B):** no regressions vs the 226/233 baseline;
  the 7 pre-existing failures stay documented. Plus the per-phase gates below.
- **Prime directive (unchanged):** a weather feature reaches the serving path
  only if it beats the last-price anchor AND seasonal naive per commodity on the
  walk-forward backtest. **Phase 1 ships the feed + the archive, not a model** -
  the band and its kill test are Phase 2. Phase 1 earns its place by producing
  real, traceable forecast rows; it makes no accuracy claim.

## API re-verification (ground rule 4, done 2026-11-14)

Checked against current sources (see M13-done.md for the live catalog check once
access exists):
- **Access:** BigQuery, Earth Engine, Cloud Storage, Maps Platform Weather API.
  **Allowlist approval** (~5-7 business days; one approval reportedly covers
  BigQuery + Earth Engine + GCS). Not open source. Real-time pricing/terms not
  fully public.
- **Ensemble scope:** BigQuery publishes **precomputed percentiles
  (p10/p25/p50/p75/p90)** for surface fields - this is the cost-critical fact:
  we pull percentiles for a few grid points, **never** the global 64-member
  hourly tensor.
- **Terms:** historical forecast backfill is **CC BY 4.0** (safe for backtest);
  **real-time** forecasts sit under Google's **experimental terms** - a genuine
  fork for commercial, vendor-facing use (Open Q3).
- **No-form companions:** PARDIG (15-min precip) and SatWeave (satellite mosaics)
  are public CC BY 4.0 - noted as a fallback, not Phase 1 scope.

## Scope

### 1. Connector + supply feed on the M11 ALU/AMED pattern
- `src/vervana/supply/weathernext.py`: the seam. Pure functions that turn a
  **BigQuery result row** (grid point x valid time x percentile columns) into
  daily-aggregated `weather_forecast` records - unit-tested offline on recorded
  fixtures. The fetch wrapper (BigQuery client) is thin IO around the pure core.
- **Without `VERVANA_WEATHERNEXT_*` creds it reports "access pending (allowlist)",
  fetches nothing, fakes nothing** - identical honesty to `supply/alu.py`,
  `supply/amed.py`. Registered in `supply/feeds.py`; honest line in
  `vervana supply status` and on `/intelligence`.
- Config: `VERVANA_WEATHERNEXT_GCP_PROJECT`, `_BQ_DATASET`,
  `_BQ_TABLE` (or Cloud Storage path), and Google credential handling via the
  standard `GOOGLE_APPLICATION_CREDENTIALS` service-account path. All in
  `.env.example` with empty values.

### 2. Origin belts in supply_zones.csv (config, never hardcoded)
Keep the 9 existing zones; add F&V origin belts (coordinates are public
district-HQ/belt points, flagged approximate like the existing zones). Proposed:
- `farrukhabad-potato` (UP), `kinnaur-apple` (HP), `ratnagiri-mango`,
  `devgad-mango` (Maharashtra).
- Final belt list reconciled against the Lalit/Vervana GRN commodity mix in
  Phase 4; Phase 1 adds the spec-named belts and verifies each commodity name
  resolves in the registry (else the zone is noted, not invented).

### 3. New table `weather_forecast` (append-only, every row traceable)
Columns: `id`, `zone`, `model_run_time` (UTC), `valid_date`, `lead_days`,
`precip_mm_p10/p50/p90`, `tmax_c`, `tmin_c`, `source`, `source_url`,
`retrieved_at` (UTC). Hand-written Alembic migration (down_revision = current
head `a1d7f3b50e92`). A forecast is **not** a price - its own table, never joined
into `price_observation`. Unique constraint on
(`zone`, `model_run_time`, `valid_date`) so a re-pull is idempotent.

### 4. Archive backfill + daily forward pull
- **Backfill 2024-present** historical forecasts (CC BY 4.0) for the zone grid
  points only, so Phase 2 features are backtestable. Bounded hard: query only the
  needed grid cells + percentile/temp columns, date-partitioned, written in
  monthly chunks with row counts shown.
- **Daily forward pull**: latest run, 15-day horizon, same zones. A
  `vervana supply weathernext-fetch` command; wired into the existing daily
  capture only after one successful manual run (M11 rule).
- **Replaces the manual IMD CSV** as the forward rain signal; `rainfall-import`
  stays as the documented fallback path (not deleted).

### 5. Surfaces + docs
- `vervana supply weathernext-fetch` (+ it shows in `supply status`),
  `.env.example`, `docs/SUPPLY.md` (the feed + the belt list + the "forecast,
  not price" boundary), `docs/RUNNING_COSTS.md` (BigQuery cost estimate).

## Tests (offline, no network - ground rule 3)
- Pure parser: a recorded BigQuery-row fixture -> expected `weather_forecast`
  records (percentile mapping, hourly->daily aggregation, lead-day math).
- "No creds" path: the feed reports access-pending and yields zero rows, zero
  fabrication (mirrors the ALU/AMED scaffold tests).
- Migration + repository round-trip (append-only, idempotent re-pull).
- All 226 currently-passing tests stay green.

## Cost (ground rule 5)
- BigQuery **query** charges only. Daily forward pull = a few grid points x 15
  days x a handful of columns = megabytes/day -> ~₹0. One-time **backfill**
  2024-present is the only real scan; bounded by column/row/partition pruning and
  estimated in the done-file before running the full backfill. Logged to
  `RUNNING_COSTS.md`. Storage (BigQuery egress + our SQLite/Turso rows) negligible.
- If the backfill estimate exceeds a few hundred rupees, I stop and show the
  estimate before running it.

## Open questions (genuine forks - need your decision)
1. **Allowlist status.** Have you submitted / been approved for WeatherNext on a
   GCP project? If **not approved**, Phase 1 ships the seam as "access pending"
   (fixture-tested, zero live rows) and the live backfill/pull activates the day
   access lands - exactly like ALU/AMED. If **approved**, I'll need the GCP
   project id + a service-account JSON path set locally (never committed) to show
   real row counts. Which is it today?
2. **Distribution to target.** Default = the **BigQuery precomputed-percentiles**
   table (cheapest, gives p10/p50/p90 directly). OK, or do you want Earth Engine
   / Zarr-on-GCS instead?
3. **Commercial ToU.** Real-time forecasts are under Google's **experimental
   terms**; historical is CC BY 4.0. For a vendor-facing commercial product this
   needs your explicit call before Phase 2 relies on **real-time** data. Plan:
   backtest on the CC BY 4.0 historical archive (clearly fine); gate real-time
   serving behind your ToU sign-off. Agree?

## Explicitly out of scope (Phase 1)
- The quantile band and any accuracy claim (Phase 2).
- Flood Hub (Phase 3), GRN import + margin watch (Phase 4).
- Deleting `rainfall-import` (kept as fallback).
- Wiring weathernext into the scheduled daily capture before one manual run
  succeeds.
- Fixing the 7 pre-existing test failures or the ruff backlog (option B: deferred).
