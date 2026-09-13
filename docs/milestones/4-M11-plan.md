# M11 - Supply-side layer: satellite + agromet feeds, Google ALU/AMED seam - PLAN

- **Status:** PLANNED (build started 2026-09-13).
- **Trigger:** Rajeev submitted Google's Agricultural Understanding partner
  interest form (review ~4-6 weeks, approval not guaranteed) and asked for the
  ALU/AMED integration to be built into the platform now.

## Scope

1. **Fallback path that works today** (the blueprint's Sentinel-2 + IMD route):
   - `connectors/sentinel2.py`: Sentinel-2 NDVI via the free Copernicus Data
     Space Statistical API -> OBSERVED `ndvi_anomaly` signals per watch zone.
   - `connectors/imd.py`: IMD district rainfall (CSV import; optional fetch URL)
     -> OBSERVED `rainfall_deficit_pct` signals.
   - `data/config/supply_zones.csv`: district watch zones (config, not code).
2. **Google ALU/AMED seam, labelled SCAFFOLD:**
   - `supply/alu.py`, `supply/amed.py`: clients that raise until partner
     endpoints/keys exist; never fabricate. Pure mapping functions (crop areas
     -> `acreage_change_pct`; field events -> `sowing_progress_pct` /
     `harvest_progress_pct`) are the real seam logic, tested offline.
3. **Chain wiring:** two new signal kinds with documented thresholds; additive
   only (existing verdict logic untouched).
4. **Surfaces:** `vervana supply` CLI (status/ndvi/rainfall-import/alu/amed),
   supply-feeds table on `/intelligence`, docs (SUPPLY.md), `.env.example`.
5. **Tests:** offline; scaffolds must prove they fetch nothing and fake nothing.

## Explicitly out of scope

- Faking ALU/AMED responses "for development" (banned; simulated data only ever
  comes through the existing labelled-fixture path).
- Scheduled/daily supply captures (a `daily_capture.sh` extension) until a live
  feed has run once by hand.
- Region/group-specific chains (still commodity-level, as M9/M10 state).
