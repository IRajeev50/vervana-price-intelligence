# M11 - Supply-side layer: satellite + agromet feeds, Google ALU/AMED seam - DONE

- **Status:** COMPLETE. 129 offline tests pass (22 new), ruff clean on all
  touched files (2 pre-existing E501 in intelligence/report.py left as found).
- **Date:** 2026-09-13.

## What was built

- **Watch zones** (`data/config/supply_zones.csv`): 9 districts across the
  profiled crops' primary regions (config, not code; district-HQ coordinates
  are a documented starting approximation).
- **Sentinel-2 NDVI connector** (`connectors/sentinel2.py`): free Copernicus
  Data Space Statistical API; fetches the current window and the year-ago
  baseline per zone, ingests OBSERVED `ndvi_anomaly` signals with both means in
  the note. No credentials, no fetch - the CLI says exactly what to set up.
- **IMD rainfall connector** (`connectors/imd.py`): district rainfall CSV ->
  OBSERVED `rainfall_deficit_pct` (from IMD's own % departure or
  actual/normal mm); optional fetch URL; without one it points at the import
  path instead of pretending.
- **Google ALU/AMED seam** (`supply/alu.py`, `supply/amed.py`,
  `supply/scaffold.py`): SCAFFOLD clients that raise `PartnerAccessPending`
  until endpoint + key are configured - they fetch nothing and fake nothing.
  The seam logic is real and pure: crop areas -> `acreage_change_pct`, field
  season events -> `sowing_progress_pct` / `harvest_progress_pct`, both fully
  tested offline. Endpoints are NOT invented: settings stay empty until the
  partner documentation lands (`TODO(partner-docs)` markers where schemas must
  be verified on first live call).
- **Chain wiring** (`intelligence/signals.py`, `intelligence/chain.py`): two
  new signal kinds with documented thresholds - sowing progress < 70% of normal
  scores production down (> 95% up); harvest progress >= 50% scores supply up
  (timing signal, never volume). Additive only; every existing verdict rule
  untouched. Until feeds connect, both kinds report `missing: not connected`
  in every outlook.
- **Surfaces**: `vervana supply status|ndvi|rainfall-import|alu|amed` CLI;
  "Supply-side feeds" table on `/intelligence` with amber scaffold pills;
  `docs/SUPPLY.md`; `.env.example`; README; OPEN_QUESTIONS entry on the
  partner-access unknowns.

## Honesty posture

- The scaffold label is everywhere the feeds appear; nothing implies ALU/AMED
  is live. Google's form quotes a 4-6 week review, approval not guaranteed.
- The platform works today without Google: NDVI + rainfall feed the production
  step; acreage/progress kinds stay honestly `missing` until a real source
  (ALU/AMED or e.g. DES acreage statistics) is connected.

## Verified end-to-end (2026-09-13)

`vervana setup` -> `intelligence outlook Sugarcane` shows the new kinds as
`missing: not connected`; `supply rainfall-import` ingested 2 observed rows;
`supply status` reports observed counts; `supply ndvi` refuses cleanly without
CDSE credentials; `/intelligence` renders the feeds table with scaffold labels.
