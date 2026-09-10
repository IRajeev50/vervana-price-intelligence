# M9 - Agricultural intelligence: from upstream signals to impact

The platform started at the mandi price. M9 adds the layer above it: signals that
move *before* the price (rain, NDVI, reservoirs, acreage, arrivals, stocks, mill
recovery, input sales, policy), joined into one explicit reasoning chain per
commodity:

```
acreage / rain / NDVI / reservoirs        ->  production outlook
production + arrivals + stocks + recovery ->  supply outlook
production vs consumption + stocks        ->  balance sheet
supply + balance                          ->  price pressure
price pressure + input sales + policy     ->  second-order impacts
                                             (farmer income, input demand,
                                              procurement cost, inflation,
                                              policy-pressure index)
```

Every arrow is a documented heuristic rule (`src/vervana/intelligence/chain.py`),
not a black box. While the platform has too little history to learn these
relationships, it can still reason over them transparently, and every conclusion
says exactly which inputs produced it.

## The honesty rules (non-negotiable)

1. **Every input is labelled.** `observed` (ingested with a named source),
   `simulated` (bundled fixture for development), or `missing` (required but
   absent - reported, never guessed). See `signals.py`.
2. **Simulated caps confidence.** Any step touching a simulated input is capped
   at 0.35 and the report verdict becomes "watchlist (simulated inputs)". The
   platform cannot issue a "signal (observed)" verdict on pretend data.
3. **Missing is an answer.** A chain step with no inputs says "insufficient
   evidence". The verdict degrades to "no signal".
4. **Honest horizons.** The outlook horizon is `crop duration + storage buffer`
   (`data/config/crop_profiles.csv`). Sugarcane: 6-8 months (10-18 month crop,
   monsoon-decided). Tomato: 4-8 weeks. The platform never claims a horizon the
   biology cannot support, and the basis is printed next to every horizon.
5. **No blending.** An observed feed of a kind drops the simulated stand-in of
   the same kind; observed and simulated values are never averaged together.
6. **Politics is pressure, not prediction.** Policy events are recorded as
   observed facts and counted into a 0-3 policy-pressure index. The platform
   never predicts election outcomes, partisan effects, or specific government
   actions.
7. **Append-only audit.** Saved reports (`vervana intelligence outlook X --save`)
   are stored unedited in `intelligence_report`, like the prospective forecast log.

## The sugar worked example

`data/samples/sugar_signals_sample.csv` bundles a labelled-simulated signal set
illustrating the 2026 sugar situation (monsoon deficit in Maharashtra/Karnataka,
acreage down, stocks tight vs consumption, an import window open). Run it:

```bash
uv run vervana intelligence outlook Sugarcane
```

Expected verdict today: **watchlist (simulated inputs)** - the chain logic works
and the direction (production down, deficit balance, price pressure up) is
computed, but until real feeds (IMD, CWC, ISMA, DGFT) are connected via
`vervana intelligence signals import-csv`, this is a development exercise, not a
live finding. `vervana intelligence outlook Sugarcane --observed-only` shows what
the platform can honestly say with live feeds alone: currently "no signal".

## Connecting real feeds

Observed signals import into `context_signal`:

```bash
uv run vervana intelligence signals import-csv my_signals.csv
# columns: signal_type, region, on_date, value_numeric, value_text, source, source_url
```

`source` is mandatory and `simulated_fixture` is rejected - an observed row
without a real source would be a provenance lie. Unknown signal types are
rejected (see `SIGNAL_KINDS` in `signals.py`).

## Forecast model review (2026-09-10)

The existing forecast harness was re-reviewed with three candidate changes
(drift baseline, baseline-median ensemble, GB with 14 lags + day-of-week
one-hot) across five synthetic regimes (random walk, weekly seasonal, trend,
level shift, seasonal+trend). Result: **no candidate beats seasonal-naive
consistently**, and the current gradient-boosting model does not clear the kill
criterion on the recorded real backtest either (63.6% vs 60.0%, needs >66%).
Decision: no model change. Baselines, models and the R7 kill gate stay exactly
as they were. The review is repeatable: same harness, same walk-forward rule.

## Track record surfaces (M10)

- **Crop portfolio** (`/intelligence`): every configured crop with its honest
  horizon plus the latest SAVED outlook's verdict, price-pressure direction,
  confidence, observed/simulated/missing coverage, as-of IST timestamp and
  derived alerts (e.g. "simulated inputs cap confidence", "N missing inputs").
  A crop with no saved outlook shows an explicit empty state - the portfolio
  never fabricates a summary.
- **Outlook calendar** (`/intelligence/history`): saved outlooks grouped by the
  date they were actually made (IST), with month navigation and a crop filter.
  Day views read ONLY the append-only `intelligence_report` store. The
  no-lookahead rule is absolute: the platform never recomputes what it "would
  have said" on a past date; generating is always a "now" action
  (`POST /intelligence/<commodity>/save` or the CLI `--save`).
- **Saved outlooks** (`/intelligence/record/<id>`, JSON at
  `/api/intelligence/records/<id>`) render the stored report unedited; the
  observed/simulated/missing labels survive the storage round-trip.
- **Region filter** (`/intelligence/<commodity>?region=...`) narrows the
  displayed input-signal table only. The reasoning chain is commodity-level and
  always uses all regions; producer-group feeds are not connected yet, and the
  UI says so rather than implying region- or group-specific analysis exists.
