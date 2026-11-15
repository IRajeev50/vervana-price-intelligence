# M16 — Repository Audit & Integration Gap Analysis

**Stage 1 deliverable** for the "evolve Vervana into a unified agricultural intelligence
platform" brief. Grounded in the actual code at `main` (580e51a), not in documentation
claims. Classifies every target module against what exists, then gives the concrete
gap analysis for the two Google integrations (WeatherNext, Flood Hub).

> Method note: everything below was read from source. Where the README or a docstring
> claims a capability, it was checked against the code that backs it. "Documented but not
> implemented" and "scaffold" are called out as such.

---

## 1. Component inventory & classification

Classification key: **OPERATIONAL** (built + validated) · **BUILT-UNVALIDATED** (built, no
real data through it yet) · **PARTIAL** · **SCAFFOLD** (honest inert seam, access pending)
· **DOC-ONLY** · **MISSING**.

### Module A — Market Intelligence
| Capability | State | Evidence |
|---|---|---|
| Agmarknet 2.0 ingest (keyless, live) | OPERATIONAL | `connectors/agmarknet.py`, CLI `ingest agmarknet`, `daily_capture.sh`, lookback + retry/backoff in `config.py` |
| `price_observation` fact table, source-class guard, integer paise, UTC store | OPERATIONAL | `models/observations.py`, `repository/prices.py` |
| Prices / Benchmark / Digest / Evidence pages | OPERATIONAL | `web/app.py` routes `/prices`, `/benchmark`, `/digest`, `/evidence/{id}` |
| Quick-commerce retail (manual panel, never scraped) | OPERATIONAL | `/panel`, `connectors/quickcommerce.py`, `digest.html` |
| Inter-mandi arbitrage / landed cost (sourcing) | PARTIAL | `/sourcing`, `freight_rate_per_tonne_km` ESTIMATE w/ `RISK[R15-FREIGHT-ASSUMPTION]`; single flat rate, state-centroid distance |
| eNAM executed prices | SCAFFOLD (stub) | `connectors/enam.py` raises `EnamAccessUnresolvedError` — no open API (OPEN_QUESTIONS #1) |
| **Mandi arrivals (quantity) time series** | **MISSING** | `price_observation` has no arrivals column; archived `raw_quote` carries only `arrival_date`, not quantity (confirmed in `forecast/features.py` header). **This is a capture-change gap, not a display gap.** |

### Module B — Weather Intelligence (WeatherNext)
| Capability | State | Evidence |
|---|---|---|
| `weather_forecast` table (zone/run/valid_date, precip p10/p50/p90, tmax/tmin, append-only, unique) | BUILT-UNVALIDATED | `models/weather_forecast.py`, migration `b2e8c4a19f07`, `repository/weather_forecast.py` |
| WeatherNext client + daily aggregation (pure, tested offline) | SCAFFOLD | `supply/weathernext.py` — `aggregate_daily()` tested; `fetch_forecasts()` raises `PartnerAccessPending` until BigQuery creds |
| WeatherUnion hyperlocal real-time (temp/humidity/wind/rain) | SCAFFOLD (key-gated) | `weather/weatherunion.py`, `models/weather.py`, migration `a1d7f3b50e92`, CLI `weather status/capture/show`; inert without `VERVANA_WEATHER_UNION_API_KEY` |
| Forecast uncertainty preserved (percentiles, not a single number) | OPERATIONAL (by design) | `ForecastRecord` keeps p10/p50/p90 + model_run_time + valid_date + lead_days |
| Model-independent weather interface | PARTIAL | `ForecastPoint`/`ForecastRecord` are provider-neutral shapes; no second provider yet to prove portability |

### Module C — Flood Intelligence (Flood Hub)
| Capability | State | Evidence |
|---|---|---|
| `flood_overlay` table (zone/issued_time, worst modelled severity, append-only) | BUILT-UNVALIDATED | `models/flood_overlay.py`, migration `c3f9a2d41e85`, `repository/flood_overlay.py` |
| Severity reducer (riverine-only, worst-modelled-wins, UNKNOWN≠safe) | OPERATIONAL (pure, tested) | `supply/floodhub.py::overlay_from_statuses`, `tests/test_floodhub.py` |
| Flood Hub client (SearchGaugesByArea → QueryGaugeForecasts) | SCAFFOLD | `fetch_overlays()` raises `PartnerAccessPending`; no gauge IDs hardcoded |
| Margin-watch riverine overlay line (belt-only) | OPERATIONAL (display seam) | `cli.py::_flood_overlay_lines`, origin-belt zones only |
| **Destination / corridor exposure (Delhi-Yamuna, warehouses, roads)** | **MISSING** | `supply_zones.csv` has 13 **origin** zones only; no destination/warehouse/corridor zone |

### Module D — Agricultural Production & Supply Intelligence
| Capability | State | Evidence |
|---|---|---|
| Reasoning chain signals→production→supply→balance→price (heuristic, provenance + confidence, fail-closed) | OPERATIONAL | `intelligence/chain.py`, `intelligence/signals.py`, `/intelligence`, `docs/INTELLIGENCE.md` |
| District crop production (DES/APY, 740 districts, 1997–2023) + rollups | OPERATIONAL | `models/crop_production.py`, `repository/crop_production.py`, CLI `crops import-apy`, `/districts` |
| Sentinel-2 NDVI anomaly (live with free CDSE creds) | OPERATIONAL (gated) | `connectors/sentinel2.py`, `supply/ndvi.py`, CLI `supply ndvi` |
| IMD district rainfall (live fetch + CSV import) | OPERATIONAL | `supply/imd_fetch.py`, `connectors/imd.py`, CLI `supply rainfall-fetch/-import` |
| Crop calendars (sowing/harvest progress) | PARTIAL | chain consumes `sowing_progress_pct`/`harvest_progress_pct` as signals; no per-commodity calendar registry — fed as signals, not modelled |
| Supply watch zones (commodity ↔ district ↔ coords) | PARTIAL | `supply/zones.py` + `supply_zones.csv`; zones carry commodities but **no mandi link** |
| Google ALU/AMED (crop/field understanding) | SCAFFOLD | `supply/alu.py`, `supply/amed.py` — access pending |

### Module E — Commodity Price Intelligence & Forecasting
| Capability | State | Evidence |
|---|---|---|
| Baselines (last-price anchor, seasonal-naive) | OPERATIONAL | `forecast/baselines.py` |
| Quantile band p10/p50/p90 (conformal + quantile-GB, monotone/non-neg clamp) | OPERATIONAL | `forecast/band.py` |
| Walk-forward backtest + WAPE + coverage + width | OPERATIONAL | `forecast/backtest.py` |
| Kill discipline (beat anchor AND seasonal; coverage ∈ [75%,88%]) | OPERATIONAL | `forecast/kill.py`, `forecast/band_runner.py` — **real result: 61 series / 45 commodities / 0 shippable** (honest negative) |
| Base features: price lags, rolling mean/std, weekly term | OPERATIONAL | `forecast/features.py` |
| **`weather` feature group** | **WIRED-BUT-EMPTY** | `features.py` — the designed entry point for WeatherNext |
| **`arrivals` feature group** | **WIRED-BUT-EMPTY** | blocked by Module A arrivals gap (capture change) |
| Margin watch (price vs band → zone) | OPERATIONAL | `forecast/margin.py` |

### Module F — Inventory & Margin Intelligence ("The Book")
| Capability | State | Evidence |
|---|---|---|
| Inventory / lot / holding model | **MISSING** | no inventory, lot, or holding table anywhere in `models/` |
| Cost stack (storage / finance / logistics / wastage / quality loss) | **MISSING** | none modelled |
| Net-realisation vs immediate-sale decision (BUY/HOLD/RELEASE/WAIT/REROUTE) | **MISSING** | `margin.py` classifies a price vs band but has no cost inputs and no hold/release logic |
| Executed-invoice ground truth (validation reference, *not* inventory) | BUILT-UNVALIDATED | `models/invoice.py` — empty until founder supplies invoices |

**Module F is the single largest genuine build in the brief.** Everything it needs
upstream (price band, margin zones, landed cost, flood/weather overlays) exists; the
commercial decision layer itself does not.

### Cross-cutting
| Capability | State | Evidence |
|---|---|---|
| Geospatial: state centroids + distance | PARTIAL | `geo.py`; no PostGIS (SQLite dev / Turso prod) — adequate for point-distance, **not** for inundation polygons |
| Data governance: provenance, source-class guard, append-only, migrations, ingest history, forecast_log, no-network tests | OPERATIONAL (a real strength) | throughout; `docs/DATA_DICTIONARY.md`, `tests/test_migrations.py` |
| Scheduling / background jobs | PARTIAL | `scripts/daily_capture.sh` (launchd/Actions) — no in-app scheduler; fine for daily cadence |
| Test suite | OPERATIONAL w/ known debt | 226/233 pass; 7 **pre-existing** failures documented (M12, gate = no regressions) |
| Lint | KNOWN DEBT | ruff reports ~353 findings under both pinned 0.6.9 and 0.16.6; no CI lint gate (M12 finding) |

---

## 2. Gap analysis — the two Google integrations

The brief's explicit first task: show **exactly** how WeatherNext and Flood Hub connect to
the current architecture. Both are **seam-complete**; neither is wired to its consumer, and
neither has access yet.

### 2.1 Google WeatherNext → price band

**Target seam:** the empty `weather` feature group in `forecast/features.py`.

```
WeatherNextClient.fetch_forecasts(zones)        [SCAFFOLD — raises until creds]
   → aggregate_daily(points)  → ForecastRecord  [BUILT + tested]
   → repository/weather_forecast  → weather_forecast table   [BUILT]
   → features.build_features: `weather` group   [EMPTY ← the missing wire]
   → band.py backtest + kill.py                 [BUILT — decides if it ships]
```

| # | Gap | Type | Blocker |
|---|---|---|---|
| W1 | Allowlist access + BigQuery project/dataset/table + creds | ACCESS | you obtain; config keys already defined |
| W2 | BigQuery row → `ForecastPoint` column mapping | BUILD (small) | must be confirmed against the live catalog on first access — deliberately **not** guessed |
| W3 | **Zone → mandi mapping** (belt weather must attach to the commodity-mandi series the band predicts) | BUILD | `supply_zones.csv` has commodities but no mandi link |
| W4 | Populate `weather` feature group from `weather_forecast` rows (lead-aligned, no leakage) | BUILD | the actual integration |
| W5 | Re-run walk-forward kill backtest **with** weather features vs the current 0/45 baseline | VALIDATE | this is the go/no-go — weather ships **only** if it beats anchor AND seasonal |

**Honest caveat already in code:** daily precip percentile = SUM of hourly percentiles
(assumes hourly independence). It's a usable band input, not an exact daily quantile; the
kill backtest is what proves or rejects it. No feature promoted for having more inputs.

### 2.2 Google Flood Hub → margin-watch overlay + chain supply step

**Target seam:** the margin-watch overlay line and the chain's "supply" node — **never** a
band feature (riverine tail-risk is an overlay, not a price input).

```
FloodHubClient.fetch_overlays(zones)            [SCAFFOLD — raises until key]
   → SearchGaugesByArea → QueryGaugeForecasts   [access-pending]
   → overlay_from_statuses(zone, statuses)       [BUILT + tested, riverine-only]
   → repository/flood_overlay → flood_overlay    [BUILT]
   → margin-watch riverine line (belt-only)      [BUILT]  /  chain supply step [candidate]
```

| # | Gap | Type | Blocker |
|---|---|---|---|
| F1 | Flood Forecasting API key (waitlist) | ACCESS | you obtain; `VERVANA_FLOODHUB_API_KEY` defined |
| F2 | Gauge discovery field mapping confirmed on first access | BUILD (small) | not guessed |
| F3 | **Destination / corridor zones** (e.g. `delhi-yamuna` ~28.611, 77.295 near Azadpur/Ghazipur) | BUILD | `supply_zones.csv` is origin-only; this is the Phase-3 corridor follow-up |
| F4 | Second overlay line (destination) on margin-watch | BUILD (small) | reuses the belt line |
| F5 | Warehouse exposure | DEFERRED | depends on Module F (no warehouse entity yet) |

**Hard caveats already enforced in code:** riverine only (not rainfall / urban
waterlogging); UNKNOWN or no-model gauge is **never** read as "no flooding"; never a band
feature; access-pending ≠ no risk.

---

## 3. Reuse-vs-build summary (what the brief asked for)

- **Reuse as-is:** Agmarknet ingest, price fact table + provenance, forecast band + kill
  discipline, reasoning chain, crop-production layer, NDVI + rainfall feeds, both Google
  scaffolds, margin-watch, the web design system.
- **Extend:** `supply_zones.csv` (add mandi links + destination/corridor zones); forecast
  `features.py` (fill `weather` group); margin-watch (second overlay line).
- **Build net-new:** **Module F (The Book)** — inventory/lot + cost stack + net-realisation
  decision; and the **arrivals capture change** (store quantity going forward) that unblocks
  the `arrivals` feature group.
- **Do NOT build:** PostGIS/inundation polygons (point-distance is enough now); a parallel
  forecasting model (extend the existing one); any fabricated live feed; eNAM scraping.

---

## 4. Proposed milestone order (for your go — no code yet)

Ordered by commercial value × feasibility × data-on-hand. Each is a controlled milestone
(plan → go → build → real test output → done doc), per the standing ground rules.

1. **M17 — The Book (Module F), advisory-only.** Highest commercial value; all upstream
   inputs exist; needs **no external access**. Inventory/lot + cost stack + BUY/HOLD/
   RELEASE/WAIT/REROUTE with net-realisation vs immediate sale, every recommendation
   showing its evidence, assumptions, and what would invalidate it.
2. **M18 — Capsicum & Onion live experiments.** Validate the chain + band + Book end-to-end
   on two real commodities with different supply chains (verify actual sourcing belts first —
   don't assume Nashik/Pune weightings).
3. **M19 — Flood Hub go-live** (on access): F2–F4, incl. the `delhi-yamuna` destination zone.
   The destination-zone wiring (F3+F4) can ship **now, access-free, fixture-tested** if you
   want an early, self-contained slice.
4. **M20 — WeatherNext go-live** (on access): W2–W5, with the kill backtest as the gate.
5. **Arrivals capture change** — fold into the next Agmarknet capture touch; unblocks the
   `arrivals` feature group for M20's backtest.

No files changed by this audit beyond this document. Awaiting your go (and any reordering)
before Stage 4 implementation.
