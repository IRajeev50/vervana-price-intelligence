# M8 — Phase 2/3 expansion · DONE (the un-gated mechanics)

- **Status:** COMPLETE for everything that doesn't depend on the R5 verdict. Intraday
  modelling is deliberately deferred (see below).
- **Date:** 2026-09-10. **81 offline tests pass, lint clean.**

## Definition of done vs actual
| Criterion (Part 6) | Result |
|---|---|
| Adding a mandi is a config change, not a code change (demonstrated) | ✅ `data/config/mandis.csv` + `vervana registry sync-mandis` — edit the CSV, re-run, mandi added. No code touched. |
| …emitting the R12 cost estimate | ✅ every sync prints the observer-cost estimate: *7 mandis, 4 observers × ₹8,000/mo = ₹32,000/mo (₹3.84L/yr, 0.6% of the ₹6.6cr NCR SAM)*. `R12` tagged in `economics.py`. |
| Authenticated, rate-limited public API | ✅ `/api/v1/*` with `X-API-Key` auth (401 without) and a per-key sliding-window rate limit (429 over budget). Tested. |
| B2B benchmarking views | ✅ `/benchmark` page + `/api/v1/benchmark/{commodity}` — latest ₹/kg across every market, ranked, with the spread and evidence links. Wholesale only, never blended with retail. |
| Historical export | ✅ `vervana export <file.csv>` and `GET /api/v1/export` (streamed CSV). |
| Intraday modelling where data supports it | ⚠️ **Deferred, honestly** — the feed is a *daily* snapshot; we have no sub-daily data to model intraday. Building it now would be fabricating a capability. The daily capture is the prerequisite; revisit once sub-daily observer/quick-commerce data exists. |

## Real output (this session, against the live dev DB)
```
$ vervana registry sync-mandis
mandis in config: 7 · newly added: 0
R12 observer-cost estimate: 1 mandi(s) × 4 observer(s) × ₹8,000/mo = ₹32,000/mo
(₹384,000/yr, 0.6% of the ₹6.6cr NCR SAM). Payroll scales linearly …

$ vervana export /tmp/vervana_export.csv --commodity Onion
exported 151 rows

# GET /api/v1/benchmark/Onion  (X-API-Key: demo-key)
summary: {n_markets: 150, min: 14.1, max: 75.0, median: 57.5, spread: 60.9}
# GET /api/v1/benchmark/Onion  (no key) -> 401
```

## What was built
- `economics.py` — observer-cost model (**R12** tagged).
- `data/config/mandis.csv` + `registry sync-mandis` — config-driven mandi expansion.
- `web/api.py` — public API v1: `require_api_key` (auth + in-memory sliding-window rate
  limit), `/prices`, `/benchmark/{commodity}`, `/forecast/status` (serves
  baseline+interval when the model isn't shippable, labelled + not-advice disclaimer),
  `/export` (streamed CSV).
- `/benchmark` web page; `vervana export` CLI.
- `.env.example` documents the public-API keys + rate.

## Cost impact
₹0 fixed (all libraries / same VPS). The API's rate limiter is in-memory (per-process) —
fine for the single-VPS design; a shared limiter is only needed if we ever scale out.

## The whole plan — status
M0 · M1 · M2 · M3 · M4 · M7 · **M8** done. Remaining and **gated on you / the calendar**:
**M5** (needs your trader invoices), **M6** (blocked by the Gate 1 legal opinion), and
**M8's intraday piece** (needs sub-daily data the daily capture will not provide).
