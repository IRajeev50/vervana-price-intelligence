# M9 - Agricultural intelligence module - DONE

- **Status:** COMPLETE. 117 offline tests pass (16 new), lint clean.
- **Date:** 2026-09-10.

## What was built

- `src/vervana/intelligence/` - crop profiles, upstream signals (observed /
  simulated / missing), the five-step reasoning chain (production -> supply ->
  balance -> price pressure -> impacts), report assembly + append-only storage.
- `data/config/crop_profiles.csv` - per-crop cycle/storage/horizon config;
  adding a commodity is a data change.
- `data/samples/sugar_signals_sample.csv` - labelled SIMULATED sugar signal set.
- `data/migrations` - `a7f3c9d21b45_add_intelligence_report` (append-only audit).
- CLI: `vervana intelligence horizons`, `... outlook <commodity> [--save]
  [--observed-only]`, `... signals import-csv`, `... signals list`.
- Web: `/intelligence` index + `/intelligence/<commodity>` outlook page with the
  chain, evidence statuses and the verdict banner; nav updated.
- API: `GET /api/v1/intelligence/<commodity>` (API-key + rate-limited like the
  rest of v1).
- Docs: `docs/INTELLIGENCE.md` (rules, feeds, worked example, model review).

## Honesty design

Simulated inputs cap confidence at 0.35 and force the "watchlist (simulated
inputs)" verdict; missing inputs produce "insufficient evidence" steps and a
"no signal" verdict; only fully observed chains may say "signal (observed)".
Policy effects are reported as observed interventions + a 0-3 pressure index,
never as political predictions.

## Forecast model review

Three candidate improvements evaluated across five synthetic regimes with the
existing walk-forward harness: none beat seasonal-naive consistently, and the
current model still fails the R7 kill criterion on the recorded real backtest.
**No model change made; gates unchanged.** Details in docs/INTELLIGENCE.md.

## Explicitly not built

- No live feed connectors (IMD/CWC/ISMA/DGFT) - imports are manual CSVs until
  access and licensing per feed are settled.
- No learned supply/price models - heuristic rules only until history exists.
- No intraday or political forecasting.
