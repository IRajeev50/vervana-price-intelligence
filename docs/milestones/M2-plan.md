# M2 — Agmarknet ingest + Delhi coverage study · PLAN

- **Status:** PLAN + BUILD (founder said "develop next phase"). Built offline behind
  recorded fixtures; the **live path needs `VERVANA_DATA_GOV_IN_API_KEY`**.
- **Why this milestone matters most:** §5.1 measures whether Agmarknet's Delhi coverage
  is bad enough to beat (`R5`). If same-day coverage > 90%, the coverage edge does not
  exist and only intraday timing remains. This is the first experiment that can kill or
  validate the product thesis.

## Definition of done (Part 6)
Real rows in the DB (counts + samples shown); a deliberate API failure handled without
data loss; the Delhi coverage report exists with the **R5 verdict recorded**.

## Honest scope note
Without the API key I cannot produce the *real* R5 verdict. I build the full ingest +
coverage machinery and run it against a **clearly-labelled synthetic fixture** that
matches the documented schema, so the code is proven correct and produces a real report
structure. The R5 verdict stays **PENDING-real** until run against live Delhi data.

## Key schema facts (verified, not assumed)
- Resource `9ef84268-...`; envelope keys `records/total/count/offset/limit/fields/status`.
- Record fields: State, District, Market, Commodity, Variety, Grade, Arrival_Date,
  Min_Price, Max_Price, Modal_Price — **but field naming is not standardised** across
  data.gov.in, so the parser maps candidate names case-insensitively and **fails loudly**
  on a missing required field (never silently mis-parses).
- **Prices are ₹ per quintal (100 kg).** quintal→kg is a *defined* conversion (not a bag
  guess), so Agmarknet rows get a real canonical ₹/kg via a seeded `unit_convention`.
- Agmarknet daily min/max/modal = a market's daily summary → `source_class =
  executed_summary`, `time_basis = daily_summary`, `price_low=min`, `price_high=max`,
  `price_point=modal`.

## What I build
- `ingest_run` table (started/finished, rows_in, accepted, rejected + reasons, raw path).
- Connector interface (pluggable, disableable via config).
- `AgmarknetConnector`: key-from-env, pagination (1000 cap), exponential backoff,
  400/429 handling that pauses rather than hot-retries, raw payload stored before parse,
  schema-robust field mapping, missing/zero-price handling, market/commodity resolution
  via the M1 registry (unresolved → rejected + proposed alias enqueued, never guessed).
- Separate `backfill` (historical date range) vs `daily` (snapshot capture).
- Coverage study (§5.1): % commodity-days reported, reporting-lag distribution,
  implausible-value count, per-commodity breakdown, and the **R5 verdict rule**.
- Recorded fixture + offline tests; a separate opt-in live test (skipped without key).
- CLI: `ingest agmarknet daily|backfill`, `coverage report`.
- New RISK tags: `R5-COVERAGE-EDGE` (coverage study), `R4-WEAK-GROUND-TRUTH` (where
  Agmarknet quality is asserted).

## Tests (offline)
Field mapping incl. mixed-case + missing-field failure; zero/missing price rejected with
reason; quintal→kg canonical; unresolved market rejected + enqueued; ingest_run recorded;
a simulated fetch failure leaves no partial data; coverage report computes the metrics and
emits an R5 verdict string on fixture data.

## Cost
₹0 fixed (no new infra; `requests`/`httpx` is a light dep). Live API is free (GODL-India).
