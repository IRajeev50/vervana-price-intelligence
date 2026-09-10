# M7 — Additional connectors · DONE

- **Status:** COMPLETE. All four M7 connectors exist behind the common interface and each
  is independently disableable via config (proven by test). **75 offline tests pass.**
- **Date:** 2026-09-10. (Quick-commerce was delivered earlier with the HoReCa work.)

## Definition of done vs actual
| Connector | Result |
|---|---|
| **eNAM** (§4.4) | ✅ Stub with the common interface; `fetch_raw` raises `EnamAccessUnresolvedError` — no open API exists (OPEN_QUESTIONS #1). Ready to slot in when access is resolved. |
| **Field observers** (§4.3, R11) | ✅ `Observer` model records **whether the observer trades in the commodities they report**; every observation carries `observer_id`, so conflicted reports are always filterable. CSV ingest → `quote_indicative` rows. ASR (voice→text) is a documented stub (external/metered). |
| **Quick-commerce** (§4.5, R10) | ✅ (earlier) manual-panel CSV only; vendor-feed stub refuses to run; **no scraper**. |
| **Context signals** (§4.6) | ✅ `context_signal` table (weather/diesel/festival) — **features, not prices**; CSV ingest; a test proves they land in `context_signal`, never `price_observation`. |
| Each disableable via config without breaking anything | ✅ `test_connectors_disable_via_config` — `VERVANA_DISABLED_CONNECTORS` disables each. |

## Real behaviour (from tests)
- eNAM: `fetch_raw()` → refuses (stub), never fabricates data.
- Observer: a conflicted observer (`trades_in_reported=True` → `is_independent=False`) can
  still submit, but every quote carries their id and independence for filtering (R11).
- Context: 3 signals (diesel/weather/festival) imported to `context_signal`; **0**
  price_observation rows created.

## Risk tags added
- `R11-RECORDER-CONFLICT` (observer.py) — the independence flag is mandatory.
- `R10-QCOMM-SOURCING` (quickcommerce.py, earlier) — vendor-feed stub.

## New CLI
`ingest observer-csv`, `ingest context-csv`, `ingest enam` (reports the stub).

## Cost impact
₹0 fixed. ASR for observer voice notes (when wired) is **variable** per-audio-minute and
carries a residency decision — tracked in RUNNING_COSTS, not incurred.

## Still open
- **eNAM access method** (OPEN_QUESTIONS #1) — the connector waits on it.
- **ASR provider** for observer voice notes — a cost + residency choice when field
  observers go live.
