# M15 - Phase 3: Flood Hub riverine risk overlay (narrow on purpose) - PLAN

- **Status:** PLANNED (2026-11-14). No code until Rajeev's go.
- **Working gate (option B):** no regressions vs the 239/246 baseline.
- **The one boundary that defines this phase:** Flood Hub forecasts **riverine
  flooding** - NOT rainfall, NOT urban waterlogging, NOT crop stress. It is a
  **tail-event risk OVERLAY**, **never a model feature** and never an input to the
  price band. It is labelled **riverine-only** everywhere it appears.

## API re-verification (ground rule 4, done 2026-11-14 against the official RPC docs)

- Host `floodforecasting.googleapis.com/v1`. **Free but API-key + activation
  gated** (waitlist) - so, like WeatherNext, this ships as an **access-pending
  seam** until a key exists.
- Methods: **`SearchGaugesByArea`** (by `region_code` or a `loop` polygon) and
  **`QueryGaugeForecasts`** (returns a `ForecastSet` per gauge; default look-back
  ~1 week).
- **`Gauge`**: `gauge_id`, `location`, `site_name`, `river`, `country_code`,
  `quality_verified`, `has_model`.
- **`FloodStatus`**: `gauge_id`, `gauge_location`, `issued_time`,
  `forecast_time_range`, `forecast_trend`, **`severity`**, `source`.
- **`Severity` enum (verified):** `EXTREME`, `SEVERE`, `ABOVE_NORMAL`,
  `NO_FLOODING`, `UNKNOWN`, `SEVERITY_UNSPECIFIED`. **`ForecastTrend`:** `RISE`,
  `FALL`, `NO_CHANGE`. These real names let the severity mapping be written
  without guessing; the live request stays inert until the key lands.
- India is Flood Hub's deepest coverage (CWC's 1,000+ gauges); exact gauge
  presence per belt is confirmed by `SearchGaugesByArea` on first access.

## Scope

### 1. Connector + feed (`supply/floodhub.py`), access-pending seam
- `FloodHubClient(PartnerFeed)` gated on `VERVANA_FLOODHUB_API_KEY`. Reports
  "access pending (waitlist)" in `supply status` / `/intelligence`; **fetches
  nothing, fakes nothing** until the key exists (same as WeatherNext/ALU/AMED).
- **Pure, tested now:** `overlay_from_statuses(zone, statuses)` -> a
  `FloodOverlay` (the zone's **max** severity among its gauges in the next 7
  days, the trend, the issued time, the window). Severity ordering uses the
  **verified enum** (EXTREME > SEVERE > ABOVE_NORMAL > NO_FLOODING). A gauge with
  `has_model=false` / `UNKNOWN` is ignored, never counted as "no flood."
- **Live path (inert until key):** `SearchGaugesByArea` over each zone's
  area + the transport-corridor regions feeding the 32 mandis, then
  `QueryGaugeForecasts`; **no gauge IDs are hardcoded** - gauges are discovered by
  area on first access (confirmed against the live schema then).

### 2. New table `flood_overlay` (append-only, traceable)
`zone`, `severity` (string enum), `trend`, `issued_time`, `valid_from`,
`valid_to`, `source`, `source_url`, `retrieved_at`. Its own table - a flood
overlay is neither a price nor a forecast feature. Idempotent on
(zone, issued_time).

### 3. Surfaces (overlay visible, labelled riverine-only)
- `vervana supply floodhub-fetch` (access pending -> stores nothing).
- `supply status` + `/intelligence` supply-feeds table: the FloodHub scaffold row.
- **Margin watch gets a flood line:** for a commodity, show the riverine overlay
  of its **origin belts** (from `supply_zones.csv` commodities) -
  "supply shock possible (riverine flood ABOVE_NORMAL near <belt>, rising)" or,
  when access is pending / no data, an explicit "no riverine overlay - Flood Hub
  access pending". Never silence that could be mistaken for "no risk".
- Into the intelligence chain as a **labelled** signal kind
  (`flood_risk_riverine`), additive only, never a band feature.

### 4. Docs
- `docs/SUPPLY.md` (the overlay, the riverine-only boundary, the gauge-by-area
  mapping), `.env.example`, `docs/RUNNING_COSTS.md` (free API -> ₹0).

## Tests (offline, no network)
- `overlay_from_statuses`: max-severity selection across gauges, EXTREME beats
  ABOVE_NORMAL, `UNKNOWN`/no-model ignored, empty -> None (not "no flood").
- Access-pending: no key -> reports pending, fetch raises, stores nothing.
- Feed registry lists floodhub as scaffold.
- `flood_overlay` repository round-trip (idempotent on zone+issued_time).
- Margin-watch overlay line renders from a fixture overlay and from the
  access-pending state. All 239 currently-passing tests stay green.

## Open questions (genuine forks)
1. **Access:** do you have a Flood Forecasting API key / activation? If **not**
   (expected), Phase 3 ships the access-pending seam (fixture-tested, zero live
   rows); live gauge discovery activates the day the key lands. If **yes**, give
   me the key locally (never committed) and I'll show real gauge counts for the
   belts.
2. **Gauge mapping:** discover gauges **by area** (`SearchGaugesByArea` over each
   belt + corridor) at fetch time - recommended, no hardcoded gauge IDs that
   could silently rot. Agree, or do you want a curated gauge list in config?
3. **Corridors:** map overlays to origin **belts** now (the 13 supply_zones), and
   add explicit transport-corridor regions (belt->Delhi) as a follow-up once the
   belt overlays are proven live. OK to start belt-only?

## Explicitly out of scope (Phase 3)
- Any use of flood data as a band/price **feature** (forbidden by design).
- Rainfall or waterlogging (Flood Hub is riverine-only).
- GRN import + the rejection-vs-weather test (Phase 4).
- A new web page (the overlay rides the existing `/intelligence` feed table +
  the margin-watch surface; the band has no dedicated page yet).
- Fixing the 7 pre-existing failures / ruff backlog (option B: deferred).
