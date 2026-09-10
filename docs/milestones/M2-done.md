# M2 — Agmarknet ingest + Delhi coverage study · DONE (offline)

- **Status:** COMPLETE offline. **The real R5 verdict is PENDING the API key** — the code
  is built and proven against a synthetic fixture; it produces the real verdict the moment
  `VERVANA_DATA_GOV_IN_API_KEY` is set and `vervana ingest agmarknet` runs against live Delhi
  data.
- **Date:** 2026-09-10. **Branch:** `m1-data-model` (continued). **56 tests pass, lint clean.**

## Definition of done vs actual

| Criterion (Part 6) | Result |
|---|---|
| Real rows in the DB (counts + samples) | ⚠️ **Fixture rows**, not live (no key). 8 in → 4 accepted / 4 rejected; samples shown below. Live path identical, gated on the key. |
| A deliberate API failure handled without data loss | ✅ `test_fetch_failure_leaves_no_partial_data` — a raised fetch records `ingest_run.status=failed` with the error and writes **zero** price rows. |
| Delhi coverage report exists with **R5 verdict recorded** | ✅ report runs; verdict emitted and **labelled `[FIXTURE DATA — NOT THE REAL VERDICT]`**. `RISK[R5]` is now a live code tag, verdict PENDING-until-live. |

## Real output (captured this session, offline via the fixture)

```
$ vervana ingest agmarknet-file tests/fixtures/agmarknet_sample.json
in=8 accepted=4 rejected=4
  rejected [1]: missing_or_zero_price
  rejected [1]: unresolved_commodity: Dragon Fruit
  rejected [1]: range_disorder
  rejected [1]: unresolved_market: Some Random Mandi

# price_observation rows (commodity_id, source_class, low, high, point, canonical ₹/kg paise, unit)
  (1, 'executed_summary', 120000, 150000, 135000, 1350, 'Quintal')   # Potato ₹13.50/kg
  (2, 'executed_summary', 200000, 260000, 230000, 2300, 'Quintal')   # Onion  ₹23.00/kg
  (1, 'executed_summary', 125000, 145000, 135000, 1350, 'Quintal')   # Keshopur Potato
  (2, 'executed_summary', 210000, 250000, 230000, 2300, 'Quintal')   # mixed-case-keys Onion

$ vervana coverage report --market Azadpur --days 5
Agmarknet coverage study — Azadpur
  window: 2026-09-06 .. 2026-09-10  (5 days)
  commodities tracked: 2
  expected commodity-days: 10
  reported: 3  (coverage 30.0%)
  same-day: 2  (same-day coverage 20.0%)
  implausible values: 0
  reporting-lag histogram (days->count): {0: 2, 1: 1}
  per-commodity coverage:  Onion 40.0%   Potato 20.0%
  VERDICT (R5): [FIXTURE DATA — NOT THE REAL VERDICT] COVERAGE GAP OF 80.0% ...
```

## What was built
- **`ingest_run`** table + migration (started/finished, rows_in/accepted/rejected, reason
  counts, raw-payload path, error).
- **Connector interface** (`connectors/base.py`) — pluggable, disableable via
  `VERVANA_DISABLED_CONNECTORS` (tested).
- **`AgmarknetConnector`**: key-from-env, pagination (1000 cap), exponential backoff, 429
  pause / 400 loud-fail, raw payload archived before parse, **schema-robust case-insensitive
  field mapping that fails loudly** on a missing field, missing/zero-price + range-disorder
  rejection, market/commodity resolution via **verified** registry aliases only (unresolved →
  rejected with reason, never guessed), quintal→kg canonical via seeded `unit_convention`.
- **Coverage study** (`analytics/coverage.py`, §5.1): % commodity-days reported, same-day
  coverage, reporting-lag histogram, implausible-value count, per-commodity breakdown, and
  the **R5 verdict** (refuses to claim a real verdict on non-live data).
- CLI: `ingest agmarknet` (live), `ingest agmarknet-file` (offline payload), `coverage report`.
- **Live opt-in path** exists (`fetch_raw`); tests never touch the network (Part 1.5).

## Risk register
Now **3 live code tags**: `R4-WEAK-GROUND-TRUTH` (connector, where Agmarknet is recorded as a
summary — explicitly *not* ground truth), `R5-COVERAGE-EDGE` (coverage study), `R9-NOT-IP`
(registry). All PENDING.

## Honest status of the experiment
The machinery is correct, but **the question M2 exists to answer — does Delhi have a coverage
gap? — is still unanswered.** It cannot be answered without the API key. On the first live
pull, expect a wave of `unresolved_commodity` rejections (Agmarknet's real vocabulary, e.g.
"Bhindi(Ladies Finger)", won't all match the English seed) — that's the alias-backlog work in
OPEN_QUESTIONS #9, not a bug. The coverage verdict is deliberately un-claimable until then.

## Deviations from plan
- Dropped the "auto-enqueue a proposed alias on unresolved" idea for M2: enqueuing needs a
  canonical target we don't have for a genuinely unknown name. Unresolved rows are **rejected
  with the name recorded** instead; fuzzy-assisted enqueue is noted for M3 (OPEN_QUESTIONS #9).

## Cost impact
₹0 fixed. `httpx` is light; the Agmarknet API is free (GODL-India). Raw payloads archived to
local disk.

## Next
Either (a) **the API key** so I run the real coverage study and record the true R5 verdict, or
(b) **M3 — serving layer** (API + dashboard + WhatsApp digest with provenance), which can be
built on fixture/demo data and gives the business something to show before the forecast. My
recommendation: get the key and settle R5 first — it's the cheapest way to learn whether the
core thesis holds.
