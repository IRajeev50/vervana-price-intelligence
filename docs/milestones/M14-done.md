# M14 - Phase 2: weather-aware quantile price band + margin watch - DONE

- **Status:** DONE (2026-11-14). Branch `m14-phase2-price-band`.
- **Decisions applied:** both bands (conformal baseline + quantile-GB challenger);
  per-commodity **majority** roll-up; **3a** - p10/p50/p90 with coverage window
  **[75%, 88%]**.
- **Gate (option B):** no regressions vs the 231/238 baseline. Met - 239 passed,
  the identical pre-existing 7 failed.

## What was built (files)

- `forecast/features.py` - shared feature matrix (price lags, rolling mean/std,
  weekly term). **Weather and arrivals feature groups are wired but EMPTY.**
- `forecast/band.py` - `Band(p10,p50,p90)`; `conformal_band` (split-conformal,
  the baseline-to-beat AND the labelled fallback) + `quantile_gb_band`
  (challenger). Monotone p10<=p50<=p90, lower bound clamped at 0.
- `forecast/backtest.py` - added **WAPE**; added `walk_forward_band` (p50
  MAE/WAPE/directional + band coverage + mean width).
- `forecast/kill.py` - `evaluate_band_kill` (p50 beats anchor AND seasonal on MAE
  and WAPE, coverage in [75%,88%]); `decide_commodity` (majority); persistence +
  fail-closed `load_band_decision` from `data/backtests/band_latest.json`.
- `forecast/band_runner.py` - backtest across the store, per-commodity roll-up.
- `forecast/margin.py` - `margin_watch(price, band)` decision surface.
- `forecast/scenarios.py` - weather-gated scenario labels (inert until weather).
- `cli.py` - `vervana forecast band`, `vervana forecast margin-watch`.
- Docs: INTELLIGENCE.md (band + kill + with/without weather), RISK_REGISTER
  (R7 band note), RUNNING_COSTS (₹0). Tests: `tests/test_band.py` (8).

## HONEST FINDING that changed the plan: arrivals are not stored

The plan assumed Agmarknet **arrivals** were in the store. They are **not**:
`PriceObservation` has no arrivals column, and the archived `raw_quote` carries
only `arrival_date`, not the arrivals quantity. So the arrival-shock feature and
the `rain-crushes-arrivals` scenario **cannot be built from existing data** - they
need a capture change (store arrivals going forward). Dropped from Phase 2
features and documented as a wired-but-empty group, not faked.

## Real output (the honest negative result)

```
$ uv run vervana forecast band
Price-band backtest (expanding-window walk-forward, p10/p50/p90)
series=61  commodities=45  shippable=0
...
Onion                    2     1     no      # 1/2 mandis -> not a majority
...
No commodity's band beat the anchor + seasonal with in-window coverage —
serving the labelled baseline band everywhere (honest negative result).
```
- **0 of 45 commodities ship.** The deepest series is ~27 days, so each
  walk-forward has only ~6-13 test points - too thin for a real win, and there is
  no weather feature yet. This is the expected, documented outcome, not a reason
  to widen the gate.
- The kill is genuinely biting, not vacuous: e.g. **Potato @ Keshopur** -
  challenger p50 MAE **37.5** paise beat anchor (50.0) and seasonal (44.4), but
  coverage **89%** was just outside [75%,88%] (n=9), so it correctly does **not**
  ship.

Margin watch works against the served (baseline) band:
```
$ uv run vervana forecast margin-watch Potato Keshopur --price 18
Potato @ Keshopur — serving: baseline band (conformal) — challenger not shippable
[CAUTION] ₹18.00/kg is ABOVE the band — caution, likely overpaying
          (band p10 ₹10.50/kg / p50 ₹11.25/kg / p90 ₹11.90/kg).
```

## Test results

- **239 passed, 7 failed, 246 total.** +8 new band tests
  (`tests/test_band.py`), all green. The 7 failures are the identical
  pre-existing set (Phase 0/1 baseline). **Zero regressions.**
- `ruff@0.6.9` clean on every file this phase added/touched.

## What did NOT work / honest notes

1. **No band ships** - by data reality (thin history, no weather), not a bug. The
   machinery is proven (fixtures + real run); the result is a documented negative.
2. **Arrivals unavailable** (above) - a capture change is the follow-up.
3. **Weather absent** - the with-weather backtest is the post-approval test; the
   feature group is wired so switching it on is a one-line change.
4. **Small samples** - per-series n is 6-13; any future "win" must survive more
   history before it is trusted, even if it clears the rule once.

## Cost impact

₹0 - CPU-only (numpy + scikit-learn already deps), offline backtest. Under the
₹25k ceiling.

## Next step

Open the Phase 2 PR. On merge, **Phase 3 (Flood Hub riverine risk overlay)** - a
narrow tail-event overlay on the band page + margin watch, NOT a model feature and
NOT rainfall. Then Phase 4 (GRN import + the proprietary rejection-vs-weather test
+ the margin watch over real GRN lines). The band's real test of value comes when
(a) more daily history accrues, (b) arrivals capture is added, and (c) WeatherNext
access lands - all tracked.
