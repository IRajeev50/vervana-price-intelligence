# Arrivals capture change — DONE

The access-free gap the [M16 audit](M16-audit.md) flagged as a **capture change, not a
display change**: Agmarknet co-reports market **arrivals (metric tonnes)** in the same daily
row as price, but the connector dropped it and `price_observation` had no column for it, so
the `arrivals` feature group was WIRED-BUT-EMPTY. This stores arrivals **going forward**.

## What shipped

- **Schema** (`price_observation.arrivals_tonnes`, `Numeric(14,3)`, nullable) — migration
  `e5b1c9d72f43`, additive and **reversible** (verified up → down → up).
- **Connector** (`connectors/agmarknet.py`): the daily-state report flatten now carries
  `arrivals`; `FIELD_CANDIDATES` maps it (optional, never REQUIRED); `ingest` parses it via
  `_arrivals_tonnes` and stores it. An **unexpected arrivals unit drops the value (NULL) but
  keeps the price row**; a missing figure is NULL, **never a guessed zero**; a genuine `0.0`
  reading is kept.
- **Queryable** (`repository/prices.py`): `arrivals_series(commodity_id, market_id)` and
  `arrivals_coverage()` — the honest record of what has been captured.
- **Honesty preserved** (`forecast/features.py` docstring): the `arrivals` feature group
  stays EMPTY until enough captured history exists **and** the band is made multivariate in
  **M20's backtest**. Capture is going-forward only, so historical rows are NULL and an
  arrival-shock feature still can't be built today. An empty column beats an invented one.
- **Tests:** 7 new, offline (+ one existing connector assertion updated for the new field).

## No backfill — and why that's honest

Historical rows were captured before arrivals were mapped, so their `raw_quote` never held
the quantity. There is nothing to backfill from; existing rows stay NULL. Claiming otherwise
would be inventing data. Arrivals accrue from the next capture onward.

## Real output (dev store)
```
# migration
Running upgrade d4a7f8e63c21 -> e5b1c9d72f43, add price_observation.arrivals_tonnes
price_observation col: arrivals_tonnes NUMERIC(14, 3)      # present
Running downgrade e5b1c9d72f43 -> d4a7f8e63c21             # reverses cleanly

# capture (one Onion @ Azadpur row with arrivals=861.0 t)
ingest: 1 accepted, 0 rejected
arrivals_coverage before/after: 0 -> 1
arrivals_series (last 3): [(date(2026, 11, 15), 861.0)]
```
```
$ uv run pytest tests/test_arrivals_capture.py
7 passed

$ uv run pytest            # full suite
7 failed, 279 passed       # the 7 are the known pre-existing M12-era failures; 0 are
                           # arrivals/connector. (272->279: +7 new tests)
```
```
$ uvx ruff@0.6.9 check <touched files>
All checks passed!
```

## What this unblocks

- **M20's kill backtest** can now add an arrival-shock feature to the band once enough
  captured history exists — the `arrivals` feature group is no longer blocked by a missing
  column, only by time (history) and the multivariate wiring that is M20's job.
- **The REROUTE liquidity filter** (M18 limitation): once arrivals history exists, the
  Book's reroute ranking can down-weight thin markets instead of ranking a high print from a
  low-volume hill mandi above a deep production market.

## Honest limitations / deferred

- **Going-forward only** (no backfill, as above) — the feature and the liquidity filter both
  need history to accumulate first.
- **Feature group still empty** by design — capture ≠ a usable feature yet (M20).
- **Acceptance criteria**: met (additive reversible migration; arrivals stored where the
  source reports them; NULL ≠ zero; genuine zero kept; unexpected unit drops value not row;
  queryable accessors; offline tests; no new regressions; ruff clean).
