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

## Status surfaces

- `uv run vervana supply status` - every feed, layer, state, next step, plus
  observed supply-signal counts in the store.
- `/intelligence` - the "Supply-side feeds" table shows the same states;
  scaffold rows carry the amber scaffold pill.
- `uv run vervana supply alu` / `uv run vervana supply amed` - scaffold detail.

## Chain rules for the new kinds (thresholds documented in chain.py)

- `sowing_progress_pct` < 70 at this date -> production score -1 (area likely
  ends down); > 95 -> +1 (sowing on time/complete).
- `harvest_progress_pct` >= 50 -> supply score +1 (harvest past halfway: the
  crop is physically moving toward mandis now). It is a TIMING signal, not a
  volume signal.
