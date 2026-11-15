# M11 - Supply-side layer: satellite + agromet feeds, Google ALU/AMED seam

The intelligence chain (M9) reasons over upstream signals, but until M11 the
only way in was hand-imported CSVs. M11 connects the first real feeds and
builds the seam for the two the platform is waiting on.

## The two layers

**Fallback (works today):**

| Feed | Signal emitted | Source |
|---|---|---|
| Sentinel-2 NDVI (Copernicus Data Space, free tier) | `ndvi_anomaly` | satellite estimate, current window vs year-ago baseline |
| IMD district rainfall | `rainfall_deficit_pct` | IMD rainfall pages / CRIS district tables |

**Partner-gated (SCAFFOLD - access requested, NOT granted):**

| Feed | Will emit | What it is |
|---|---|---|
| Google ALU (Agricultural Landscape Understanding) | `acreage_change_pct` | field boundaries, crop type, field acreage; refreshes ~6-monthly |
| Google AMED (Agricultural Monitoring and Event Detection) | `sowing_progress_pct`, `harvest_progress_pct` | in-season field monitoring: sowing/harvest dates per crop season; refreshes ~15 days |

ALU gives the "what and where" (district crop map: which crop, how much area,
which season). AMED gives the "when" (sowing/harvest timing, so an arrivals
spike is forecast before it shows in mandi quotes). Both feed the existing
chain - no new black box:

```
ALU crop map (area per crop per zone, season over season) -> acreage_change_pct  -> production step
AMED sowing events  -> sowing_progress_pct   -> production step (earliest acreage signal)
AMED harvest events -> harvest_progress_pct  -> supply step (timing: crop moving to mandis)
Sentinel-2 NDVI     -> ndvi_anomaly          -> production step (live today)
IMD rainfall        -> rainfall_deficit_pct  -> production step (live today)
```

## Honesty rules (the same ones, applied harder)

1. **Scaffolds fetch nothing and fake nothing.** `AluClient` / `AmedClient`
   raise `PartnerAccessPending` until the endpoint AND key are configured.
   Their status everywhere (CLI, web) is "scaffold - access pending", never
   "connected". Google's interest-form review is measured in weeks; approval
   is not guaranteed.
2. **Endpoints are not invented.** The public docs
   (https://developers.google.com/agricultural-understanding,
   https://agri.withgoogle.com/) describe the APIs' shape but publish no
   callable endpoint. `VERVANA_GOOGLE_ALU_API_URL` /
   `VERVANA_GOOGLE_AMED_API_URL` stay empty until the partner documentation
   lands; the request code is written behind those settings and marked
   `TODO(partner-docs)` where the schema must be verified on first live call.
3. **Satellite numbers are estimates, labelled.** NDVI is vegetation vigour
   over a ~10 km box around a zone point, not measured supply; every ingested
   signal carries its source and the current/baseline means in its note.
4. **Zones are config.** `data/config/supply_zones.csv` holds district-HQ
   coordinates as a deliberate starting approximation - refining a zone to a
   growing-belt centroid is a data change.
5. **The seam logic is real and tested.** The mappings (crop areas ->
   acreage_change_pct; field events -> progress %) are pure functions with
   offline tests. When approval lands, connecting is: set 3 env vars, run the
   fetch, verify the response schema against partner docs, ingest.

## Connecting each feed

**Sentinel-2 NDVI (free):** register at https://dataspace.copernicus.eu/,
create an OAuth client (dashboard -> "OAuth clients"), then:

```
VERVANA_CDS_CLIENT_ID=...
VERVANA_CDS_CLIENT_SECRET=...
uv run vervana supply ndvi            # all zones, 30-day window + year-ago baseline
uv run vervana supply ndvi --zone nashik-onion --days 45
```

Endpoints default to the current CDSE values (`VERVANA_CDS_TOKEN_URL`,
`VERVANA_CDS_STATISTICS_URL` overridable). Auth:
https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html

**IMD district rainfall:** export a CSV from the IMD rainfall pages
(https://mausam.imd.gov.in/responsive/rainfallinformation.php) or the CRIS
portal (https://hydro.imd.gov.in/hydrometweb/DistrictRaifall.aspx), columns
`district,state,date,dep_pct` (or `actual_mm,normal_mm`), then:

```
uv run vervana supply rainfall-import my_rainfall.csv
```

The daily district rainfall distribution bulletin is a PDF; if a stable
machine-readable endpoint is found, set `VERVANA_IMD_DISTRICT_RAINFALL_URL`
and `fetch_raw` uses it.

**Google ALU/AMED (when approved):**

```
VERVANA_GOOGLE_AGRI_API_KEY=...
VERVANA_GOOGLE_ALU_API_URL=<from partner docs>
VERVANA_GOOGLE_AMED_API_URL=<from partner docs>
uv run vervana supply alu    # shows "ready" instead of "access pending"
```

Then wire the fetch into the mapping functions in `vervana.supply.alu` /
`vervana.supply.amed` and ingest the resulting signals with
`vervana intelligence signals import-csv` (or a scheduled connector run).

## WeatherNext 3 - forward weather forecast (M13, SCAFFOLD)

A **forward**-looking feed, distinct from the backward signals above: Google
DeepMind's WeatherNext 3 (hourly init, 15-day horizon, 64-member ensemble). It is
the forward rain/heat signal the **Phase-2 price band** will try to beat the
last-price anchor with - it **replaces the manual IMD CSV ritual** as the
forward rain signal (`rainfall-import` stays as the documented fallback).

Boundaries, enforced in code:
- A **forecast is not a price and not a chain signal.** It is stored in its own
  `weather_forecast` table (precip p10/p50/p90, tmax/tmin per zone per valid
  date) and is **never** joined into `price_observation`.
- **Cost-safe by design:** BigQuery publishes precomputed surface percentiles, so
  we query only the grid points nearest our ~13 origin belts - never the global
  64-member hourly tensor. Daily forward pull is megabytes; the one-time
  2024-present historical backfill (CC BY 4.0) is the only real scan and is
  bounded by column/partition pruning.
- **Daily precip percentile = sum of the hourly percentile** over the day. That is
  a usable band, not an exact daily quantile (it assumes hourly independence);
  the band only reaches serving in Phase 2 if it beats the anchor on the
  walk-forward backtest - the approximation is tested there, never assumed.
- **Access is allowlist-gated and NOT granted yet.** Until
  `VERVANA_WEATHERNEXT_GCP_PROJECT` / `_BQ_DATASET` / `_BQ_TABLE` + a credentials
  path are set, `vervana supply weathernext-fetch` reports "access pending" and
  stores nothing - it never fabricates a forecast row. The raw BigQuery
  row -> forecast-point mapping is confirmed against the live catalog on first
  access; only the model-independent daily aggregation is written (and tested)
  now.
- **Terms:** historical backfill is CC BY 4.0 (safe for backtest); real-time
  forecasts sit under Google's experimental terms - commercial, vendor-facing
  reliance on real-time data is gated on an explicit terms sign-off (Phase 2).

## Status surfaces

- `uv run vervana supply status` - every feed, layer, state, next step, plus
  observed supply-signal counts in the store.
- `/intelligence` - the "Supply-side feeds" table shows the same states;
  scaffold rows carry the amber scaffold pill.
- `uv run vervana supply alu` / `uv run vervana supply amed` - scaffold detail.
- `uv run vervana supply weathernext-fetch` - fetch + store daily forecasts;
  reports "access pending" and stores nothing until the allowlist grants access.

## Chain rules for the new kinds (thresholds documented in chain.py)

- `sowing_progress_pct` < 70 at this date -> production score -1 (area likely
  ends down); > 95 -> +1 (sowing on time/complete).
- `harvest_progress_pct` >= 50 -> supply score +1 (harvest past halfway: the
  crop is physically moving toward mandis now). It is a TIMING signal, not a
  volume signal.

## Flood Hub - riverine flood risk overlay (M15, SCAFFOLD)

A **tail-event risk overlay**, deliberately narrow. Google Flood Hub forecasts
**riverine** flooding (CWC's 1,000+ gauges across India) - **NOT rainfall, NOT
urban waterlogging, NOT crop stress**. It is labelled **riverine-only** everywhere.

Boundaries, enforced in code:
- **NEVER a band/price feature.** It is an overlay beside the band / margin watch
  and a labelled chain signal (`flood_risk_riverine`), never a forecast input.
- **Overlay mapping (verified `Severity` enum):** a zone's flag is the WORST
  modelled severity among its gauges over the 7-day window -
  `EXTREME > SEVERE > ABOVE_NORMAL > NO_FLOODING`. An `UNKNOWN` or un-modelled
  gauge is **ignored, never counted as "no flooding"**; a zone with no usable
  gauge yields **no overlay** (distinct from a genuine `NO_FLOODING`).
- **Gauges discovered by AREA** (`SearchGaugesByArea`) per belt on first access -
  no gauge IDs are hardcoded. Belt-only for now; transport corridors (belt->Delhi)
  are a follow-up once belt overlays are proven live.
- **Access is waitlist + API-key gated and NOT granted.** Until
  `VERVANA_FLOODHUB_API_KEY` is set, `vervana supply floodhub-fetch` reports
  "access pending" and stores nothing; the margin-watch overlay line says so
  explicitly ("access pending - NOT 'no flood risk', just no data"), so silence is
  never mistaken for safety.
- Stored append-only in `flood_overlay` (its own table; a flood flag is neither a
  price nor a forecast feature), idempotent on (zone, issued_time).

## M18 — Capsicum & Onion belt validation (evidence-cited)

The master brief's one rule for the first live experiments: *verify actual sourcing
belts first — don't assume Nashik/Pune weightings.* M18 did that for Onion and
Capsicum, from two sources in combination:

1. **Agmarknet coverage** (what our own store already holds) — which mandis report
   each commodity, by state. This is **consumption-skewed** (Tamil Nadu tops the raw
   report counts because it has many reporting mandis), so coverage alone is NOT a
   production belt. It is used only to confirm a belt is observable in our data.
2. **Authoritative production statistics, cited** — NHB monthly/horticulture
   estimates and CEIC's compilation of them.

**No belt carries an invented volume weight.** Mandi *arrivals quantity* is not stored
(the capture-change gap), so belt *shares* cannot be computed from our data and are not
claimed. Belts are recorded as present/evidenced, with provenance, not weighted.

### Belts added (config, not code — `data/config/supply_zones.csv`)

| Zone | District / State | Commodity | Evidence |
|---|---|---|---|
| `gadag-onion` | Gadag, Karnataka | Onion | Karnataka ~13–15% of national onion (NHB); fills the belt the Onion profile already claimed but had no zone for |
| `kullu-capsicum` | Kullu, Himachal Pradesh | Capsicum | HP = seasonal summer/rainy bell-pepper supplier to the plains; Kullu valley dominates our Capsicum coverage (Bhuntar, Kullu, Nagrota, Rohroo) |
| `kolar-capsicum` | Kolar, Karnataka | Capsicum | Karnataka leads on protected-cultivation capsicum (NHB/CEIC) |

Onion kept its existing `nashik-onion` + `indore-onion` zones (Maharashtra ~42%, MP
~15%). Capsicum had **no zone at all** before M18.

### Market coordinates (config — `data/config/market_coords.csv`)

16 belt + destination mandis were given **district-HQ / town-point coordinate
approximations**, each with a `source`. These are deliberate approximations (same
convention as the zones above), not surveyed points. They activate the Book's (M17)
outbound-freight and REROUTE estimates: a market without coordinates stays honestly
"distance unknown", never a guessed zero. Apply with `vervana registry market-coords`
(idempotent). The coordinate approximation **compounds the R15 freight-rate assumption**
— a REROUTE's rupee figure is only as precise as both.

### Known limitation (tied to the arrivals gap)

The Book's REROUTE ranks alternative mandis by **net executable price minus freight**,
with **no liquidity/volume filter** — because arrivals quantity is not stored. Thin
hill-market prints (e.g. a high Onion price at an HP mandi that mostly *imports* onion)
can therefore rank above deep production markets. The verdict shows its full working so
the operator can judge; a volume-aware filter unblocks with the arrivals capture change.

## M19a — destination flood zones (Flood Hub, access-free slice)

Flood Hub (above) is keyed to **origin growing belts**. M19a adds the **destination** side:
a consumption hub near a river corridor, so an outbound lot can carry a riverine tail-risk
flag on its *logistics*, never its price.

- **`data/config/destination_zones.csv`** — a destination zone (`delhi-yamuna`, the Yamuna
  corridor at Delhi, ~28.61,77.29) with the Delhi hub markets it covers and a gauge
  search-area radius for when API access lands. Kept **separate from `supply_zones.csv`** so
  origin belts (which carry commodities) and destination zones never blur.
- **Book wiring** (`book/service.py`): a lot's intended market → destination zone →
  `latest_overlay_for_zone` → `FloodFlag` passed to the decision engine (which has supported
  and tested the flood path since M17). A reroute into another flood-exposed hub is marked
  **not flood-safe**, so the Book never moves stock from one flooded destination to another.
- **The honest line:** every lot shows a destination flood line — the overlay severity with
  its source when present, or *"access pending — NOT 'no flood risk', just no data"* when the
  zone is mapped but has no overlay, or *"not in a mapped flood zone"* when it maps to none.

### The access-free overlay path (`vervana supply floodhub-record`)

Until the Flood Forecasting API key lands (M19b), an overlay can be recorded from an
**official CWC/IMD riverine bulletin** with a **mandatory `source_url`** and a severity that
must be a verified enum value — nothing is invented, nothing fabricated. This lights the
flood-driven REROUTE path today and is identical in effect to a live pull once access lands.

**Riverine-only, never a price/band feature, access-pending ≠ no risk** — all enforced as in
M15. The live gauge pull (`floodhub-fetch`) stays access-gated and fabricates nothing.
