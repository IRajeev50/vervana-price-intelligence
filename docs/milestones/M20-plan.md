# M20 — WeatherNext go-live — PLAN

Status: **PLAN, awaiting go.** No files change until the forks below are chosen.
Builds on [M13](M16-audit.md) (the WeatherNext seam) and the arrivals/belt work in
[M18](M18-done.md) / [arrivals-capture](arrivals-capture-done.md).

## The access reality (read first — a STAGE-4 stop-for-approval item, like M19)

WeatherNext 3 is **allowlist + GCP + BigQuery + credentials gated, and NOT granted.** Until
`weathernext_gcp_project` / `_bq_dataset` / `_bq_table` / `_credentials_path` are set, every
fetch raises `PartnerAccessPending` and **nothing is ingested or fabricated.** I cannot pull
forecasts, and I will not invent them. The exact BigQuery column names are confirmed against
the live catalog on first access — *"we do not guess them here"* (the scaffold's own words).

## The deeper honesty — M20's payoff is doubly gated, and may be a null result

The value of WeatherNext is one thing: **a price band clears the kill bar and lifts a
commodity off WAIT.** Today **0 / 45 clear it.** Getting there needs three things, and only
the first is a milestone deliverable:

1. **Live weather data** (access — M20b).
2. **A multivariate band** — the band backtest is **univariate today** (`build_features` is
   price-lags only; `backtest_bands` challenges with a price-only quantile-GB). There is *no*
   weather code path in the band yet; the "weather feature group" is a docstring bullet, not
   a wire. Making the band multivariate depends on the **real** data's shape and the
   **confirmed** BQ columns, so it belongs with M20b, not before.
3. **Enough overlapping weather+price history** — which only accrues after access lands.

The band_runner docstring already states the honest prior: *"with short history and no
weather features yet, few or no [bands ship]."* **A re-run that still ships nothing is a
valid, reportable outcome, not a failure to hide.** M20 will not claim weather helps until a
walk-forward backtest on real data proves it beats the anchor + seasonal baseline.

So M20 splits like M19:

- **M20a — access-free, non-speculative (build now).** The pieces that are certain and
  stable regardless of the live schema: the **belt→mandi link** (audit **W3**) and a **pure,
  fixture-tested weather-feature builder** that aligns stored `weather_forecast` rows to a
  price series (**W4 seam, dormant**). No change to the live band or kill gate.
- **M20b — access + the real test (held for your approval).** GCP/BQ/credentials; confirm
  the BQ column mapping against the live catalog (**W2**); first pull; make the band
  multivariate; **re-run the kill backtest as the gate (W5)** — the honest test, null result
  included.

## Why not build the multivariate band now?

Because it would be speculative. The feature's exact inputs depend on the confirmed BigQuery
column names and the real distribution of the daily-percentile approximation (which the
scaffold flags as *"a usable band, not an exact daily quantile"*). Wiring it before the data
exists risks building to a guessed schema and — worse — tuning against no data, which edges
toward fabrication. M20a builds only what the live schema cannot invalidate.

## Scope — M20a (default plan: config + a dormant pure seam, no migration)

1. **Belt→mandi link (W3)** — the band predicts a `(commodity, mandi)` series, so belt
   weather must attach to the right series. Add the mapping (e.g. `nashik-onion` → the Onion
   series at Lasalgaon/Nashik; `gadag-onion` → Onion at Gadag; `kullu-capsicum` → Capsicum in
   the HP belt mandis). Config + loader, access-free, explicit — never proximity-guessed.

2. **Weather-feature builder (W4 seam, dormant & pure)** — a function that, given a series'
   dates and the stored `weather_forecast` rows for its mapped belt zone(s), returns an
   aligned weather feature vector (see Fork 3), or an empty/NaN-free result when no weather
   exists. **Tested offline on fixture `weather_forecast` rows.** It does NOT enter the live
   band challenger — it is ready for M20b to wire once real data and the confirmed columns
   exist.

3. **Findings doc** — `docs/milestones/M20a-done.md`: the belt→mandi links, the feature
   builder demonstrated on fixture weather rows, and an explicit "M20b blocked on access +
   the kill re-run is the real test (null result possible)" note.

**Migration:** none (belt→mandi is config; `weather_forecast` table already exists).
**Tests:** belt→mandi link load + the feature builder on fixtures — all offline, no network.

## Honesty constraints (non-negotiable, carried from M13)

- **A forecast is never a price and never a chain signal** — `weather_forecast` is its own
  table, never joined into `price_observation`.
- **No fabricated forecast.** Data comes only from the live BQ pull (M20b) — never invented,
  never a guessed column mapping.
- **Weather enters the band only after it proves itself** on a walk-forward backtest against
  the anchor + seasonal baseline. Until then the band stays exactly as it is today.
- **A null result is reported as a result.** If weather doesn't lift any band, M20b says so.

## Decision forks

**Fork 1 — How much M20a builds access-free**
- **1a (recommended):** W3 belt→mandi link + the dormant, fixture-tested weather-feature
  builder + findings. No change to the live band/kill gate.
- 1b: W3 link only; defer even the feature builder to M20b.
- 1c: wire weather into the band challenger now — **rejected**: speculative without real data
  and the confirmed BQ columns; risks tuning against nothing.

**Fork 2 — Belt→mandi mapping representation**
- **2a (recommended):** add a `mandis` column to `supply_zones.csv` (belt → the commodity-
  mandi series it informs). One file, explicit.
- 2b: a separate `belt_mandi_map.csv`.

**Fork 3 — Weather feature definition (dormant builder)**
- **3a (recommended):** forward-window **precip p50 sum** + **heat-day count** (tmax over a
  per-commodity threshold) across the forecast horizon, aligned by `valid_date` — the obvious
  supply-stress signals, each labelled an approximation.
- 3b: precip p50 only (simpler, less signal).

**Fork 4 — Surface**
- **4a (recommended):** findings doc + a small read-only CLI (`supply weather-links`) to show
  the belt→mandi map and weather-row coverage per zone.
- 4b: findings doc only.

## Recommended path

**1a + 2a + 3a + 4a** — build the certain, access-free pieces (belt→mandi link + a dormant
fixture-tested weather-feature builder), change **nothing** in the live band or kill gate, and
report honestly. Then **stop** and hand M20b (GCP/BQ credentials → confirm W2 columns → first
pull → multivariate band → the kill re-run that is the real test) back to you.

## What I need from you for M20b (not M20a)

Allowlist access to the WeatherNext BigQuery percentiles table, a GCP project, and
credentials (`weathernext_gcp_project`, `_bq_dataset`, `_bq_table`, `_credentials_path`).
Then I confirm the column mapping against the live catalog before the first pull, wire the
band, and re-run the kill backtest — reporting whatever it says, a null result included.

Reply with the forks (or "defaults") and I'll build M20a.
