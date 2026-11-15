# M20a — WeatherNext belt→mandi link + dormant feature builder (access-free) — DONE

Built per [M20-plan.md](M20-plan.md) on the operator's chosen **defaults**
(1a link + dormant builder, 2a `mandis` column, 3a precip-sum + heat-days, 4a CLI + findings).
**No external access used, no credentials, no fabrication, no change to the live band or kill
gate.** The live BigQuery pull and the kill re-run (**M20b**) stay access-gated.

## What shipped

- **Belt→mandi link (W3)** — `supply_zones.csv` gains a `mandis` column; `SupplyZone.mandis`
  + `zones_for_series(commodity, mandi)` (`supply/zones.py`). Onion and Capsicum belts linked
  to the mandi series their weather informs; other belts left blank until needed, never
  proximity-guessed.
- **Weather-feature builder (W4, DORMANT)** — `forecast/weather_features.py`:
  `weather_feature_for_series` reduces a series' linked belts' latest forecast run to a
  supply-stress feature (forward precip p50 sum + heat-day count, tmax ≥ 35°C by default,
  tunable). Returns None with no link or no stored forecast — never a fabricated zero. Not on
  the live band.
- **Read-only CLI** — `vervana supply weather-links` shows the links and forecast coverage.
- **Honesty preserved** (`forecast/features.py` docstring): the weather feature stays off the
  band until M20b (live access + confirmed BQ columns + a backtest that proves it beats the
  anchor + seasonal baseline).
- **Tests:** 5 new, offline.

## Why this is bounded here (not the whole of WeatherNext)

The band is **univariate today** and the payoff — a band clearing the kill bar — is doubly
gated (live data + a multivariate band + overlapping history). Wiring weather into the band
now would mean building to a **guessed** BigQuery schema and tuning against **no** data, which
edges toward fabrication. M20a builds only the pieces the live schema cannot invalidate: the
belt→mandi link and a dormant, fixture-tested builder. The real test is M20b's kill re-run.

## Real output

**The link + coverage (dev store has no forecasts — access pending, honestly shown):**
```
$ vervana supply weather-links
nashik-onion [Onion] → Lasalgaon;Nashik;Pune(Moshi)  (no forecast (access pending))
indore-onion [Onion] → Indore APMC;Ujjain APMC;Shajapur APMC  (no forecast (access pending))
gadag-onion [Onion] → Gadag APMC;Bengaluru APMC  (no forecast (access pending))
kullu-capsicum [Capsicum] → PMY Kullu;SMY Bhuntar;SMY Nagrota Bagwan  (no forecast ...)
kolar-capsicum [Capsicum] → Bangarpet APMC;Bengaluru APMC  (no forecast (access pending))
weather feature is DORMANT until M20b (live pull + kill backtest).
```

**The builder on fixture forecast rows (offline test):** three `nashik-onion` days with
precip p50 5.0/10.0/2.5 and tmax 30/37/36 → `precip_p50_sum_mm=17.5`, `heat_days=2`
(37 and 36 clear 35°C), `zones=['nashik-onion']`. With no stored forecast → `None` (access
pending), never a zero.

### Tests
```
$ uv run pytest tests/test_weather_features.py
5 passed

$ uv run pytest            # full suite
7 failed, 284 passed       # the 7 are the known pre-existing M12-era failures; 0 in
                           # weather/supply. (279->284: +5 M20a tests)
```
```
$ uvx ruff@0.6.9 check <touched files>
All checks passed!
```

## Honest limitations / deferred

- **M20b (the real test) is blocked on access.** `weathernext-fetch` still raises
  `PartnerAccessPending`. Going live needs the GCP project + BigQuery percentiles table +
  credentials (`weathernext_gcp_project`/`_bq_dataset`/`_bq_table`/`_credentials_path`); then
  the column mapping is confirmed against the live catalog (audit **W2**) before the first
  pull, the band is made multivariate, and the kill backtest is re-run as the gate (**W5**).
- **A null result is a valid result.** With short history and the daily-percentile
  approximation, weather may not lift any band off WAIT; the band_runner prior already expects
  few or none. M20b will report whatever the backtest says.
- **Heat threshold (35°C) is a default assumption** — per-commodity calibration is an M20b
  task tuned on real data.
- **Belts without a need are unmapped** (blank `mandis`) — honest, extended when a belt's
  series is exercised.
- **Acceptance criteria**: met (belt→mandi link explicit + loaded; builder pure and
  fixture-tested; None ≠ zero for no-link / no-forecast; nothing added to the live band/kill
  gate; no migration; offline tests; no new regressions; ruff clean).
