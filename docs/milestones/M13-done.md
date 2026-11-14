# M13 - Phase 1: WeatherNext 3 as a forward weather supply feed - DONE

- **Status:** DONE (2026-11-14). Branch `m13-phase1-weathernext-feed`.
- **Decision applied:** not approved for the allowlist yet, so Phase 1 ships the
  **seam as access-pending** (fixture-tested, zero live rows, zero fabrication) -
  live backfill/pull activate the day access lands. No modelling, no accuracy
  claim: the band + kill test is Phase 2.
- **Gate (option B):** no regressions vs the 226/233 baseline. Met - see below.

## What was built (files)

- `src/vervana/supply/weathernext.py` - the seam. `WeatherNextClient(PartnerFeed)`
  gated on BigQuery config (project + dataset + table + credentials); pure
  `aggregate_daily()` (hourly `ForecastPoint` -> daily `ForecastRecord`). The raw
  BigQuery-row -> point mapping is left as a documented TODO confirmed against the
  live catalog on first access - **not guessed** (same honesty as ALU/AMED).
- `src/vervana/models/weather_forecast.py` + migration
  `b2e8c4a19f07_add_weather_forecast.py` (head now `b2e8c4a19f07`). Append-only,
  unique on (zone, model_run_time, valid_date).
- `src/vervana/repository/weather_forecast.py` - idempotent `record_forecasts`,
  `forecast_count`, `latest_run_for_zone`.
- `src/vervana/supply/feeds.py` - WeatherNext listed in `supply status`.
- `data/config/supply_zones.csv` - +4 F&V belts (farrukhabad-potato,
  kinnaur-apple, ratnagiri-mango, devgad-mango); 9 -> 13 zones.
- `src/vervana/cli.py` - `vervana supply weathernext-fetch`.
- `src/vervana/config.py`, `.env.example` - `VERVANA_WEATHERNEXT_*`.
- `docs/SUPPLY.md`, `docs/RUNNING_COSTS.md` - the feed, the boundary, the cost.
- Tests: `tests/test_weathernext.py` (6 tests).

## Real output

Scaffold is honest on both surfaces:
```
$ uv run vervana supply status
[SCAFFOLD] Google WeatherNext 3 - forward weather forecast
           state: scaffold - access pending (allowlist) - set VERVANA_WEATHERNEXT_* once approved
           emits: weather_forecast rows (precip p10/p50/p90, tmax/tmin per zone/date)

$ uv run vervana supply weathernext-fetch
Google WeatherNext 3 ... [scaffold - access pending (allowlist) ...]
... No request was made and no data was fabricated. See docs/SUPPLY.md.
nothing was fetched and nothing was faked.        # exit 0
```

Zones load and commodities resolve:
```
zones: 13
 + farrukhabad-potato ['Potato'] (27.39, 79.58)
 + kinnaur-apple ['Apple'] (31.54, 78.27)
 + ratnagiri-mango ['Mango'] (16.99, 73.3)
 + devgad-mango ['Mango'] (16.37, 73.38)
registry has 'Apple': True | 'Mango': True | 'Potato': True
```

Migration applied cleanly: `migrated to head` -> `b2e8c4a19f07 (head)`.

## Test results

- **231 passed, 7 failed, 238 total.** +5 net new passing tests
  (`test_weathernext.py`); the 6th weather test shares the file.
- The **7 failures are the identical pre-existing set** from the Phase 0 baseline
  (`test_admin_supply` x2, `test_ground_proof_upload` x2, `test_transcript`,
  `test_web` x2). **Zero regressions.** (Option B: these stay documented.)
- `ruff@0.6.9` clean on every file this phase added/touched.

## What did NOT work / honest notes

- **No live rows** - by design. Access is pending; the live BigQuery pull and the
  2024-present backfill cannot be shown until the allowlist approves. The seam is
  proven inert (raises, stores nothing) and the daily aggregation is proven on
  fixtures.
- **The daily percentile is a sum-of-hourly approximation**, labelled everywhere
  (model + aggregation + SUPPLY.md). Its validity is a Phase-2 backtest question,
  not asserted here.
- The raw BigQuery schema is **not** hard-coded - the row->point mapping is a
  TODO confirmed on first access, so no invented column names ship.

## Cost impact

₹0 today (no requests made). When access lands: daily pull ~₹0; one-time backfill
is the only real scan, bounded and estimated before running (stops for a decision
if > a few hundred rupees). Logged in `RUNNING_COSTS.md`. Under the ₹25k ceiling.

## Next step

Open the Phase 1 PR. On merge, **Phase 2 (weather-aware quantile band)** - but it
cannot show live weather features until WeatherNext access is granted. Decision
for Rajeev: (a) proceed with Phase 2 band scaffolding on existing price/arrival
features now and slot weather features in on approval, or (b) pause modelling
until access lands. Also pending: the commercial real-time ToU sign-off (Open
Q3) before any real-time data reaches the serving path.
