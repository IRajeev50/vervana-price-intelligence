# M4 — Forecasting harness · DONE (harness complete; real verdict pending history)

- **Status:** COMPLETE as a harness. The **kill criterion, baselines, walk-forward,
  decision-P&L and prospective log all work**; the *real* forecast verdict waits on ~90
  days of captured daily history (the R5 capture is building it).
- **Date:** 2026-09-10. **75 offline tests pass, lint clean.**

## Definition of done vs actual
| Criterion (Part 6 / §5.3) | Result |
|---|---|
| Baselines always computed + reported | ✅ naive, seasonal-naive, 7-day MA — every run. |
| Walk-forward, never a random split | ✅ expanding-window one-step; a test proves a flat series gives MAE 0 (no leakage). |
| MAE (₹/kg), sMAPE, directional acc, PI coverage — per model, beside baselines | ✅ see table below. |
| Decision-level P&L vs naive | ✅ buy/hold rule P&L, model vs naive. |
| SARIMA then gradient boosting; no LSTM | ✅ SARIMA(1,0,0)(1,0,0)₇ + HistGradientBoosting; **no LSTM** (forbidden). |
| Kill criterion enforced in code, fires both ways | ✅ `evaluate_kill`; tests assert both directions; `forecast status` reads stored results at runtime (fails closed). |
| Public prospective log from day one | ✅ `prospective_forecast` table + record/score; append-only, scored when actuals arrive. |

## Real output (`vervana forecast demo`, random-walk series = real F&V behaviour)
```
model                 MAE ₹/kg    sMAPE  dir.acc   PIcov  P&L vs naive
naive                     0.33     1.5%     0.0%     88%          0.00
seasonal_naive            0.87     4.1%    48.5%     46%          1.82
moving_average            0.54     2.5%    49.5%     62%          0.94
sarima                    0.35     1.6%    46.5%     85%          2.21
gradient_boosting         0.66     3.1%    49.5%     66%          2.39

model_shippable: False
gradient_boosting directional 49.5% does NOT beat seasonal_naive 48.5% by >10%
(needs >53.3%) — serving falls back to baseline + interval, labelled as such (R7).
```

## The honest finding (R7)
On random-walk data — which is what daily fresh-produce prices largely are — **gradient
boosting does not beat the naive baselines**, exactly as R7 predicted. The kill criterion
correctly refuses to ship it. This is a *feature*: the harness is built so that if the
model can't clear the bar, the product serves honest baselines + intervals rather than a
dressed-up random walk. The real verdict on *actual Delhi data* is PENDING history.

## Risk tags added (register now shows 9 live code tags)
- `R7-FORECAST-BAR` (models.py) — GB-beats-naive assumption; kill enforces it.
- `R6-MOAT-MODEL-GAP` (models.py) — **video-feature contribution = 0%** (no video features
  exist; Gate 1). So on this model the corpus defends nothing, by construction.
- `R13-RANGE-MIDPOINT` (series.py) — the modelled series collapses a range to one number.

## Cost impact
₹0 fixed (scikit-learn/statsmodels/numpy/pandas are libraries). They raise RAM/CPU during
the nightly backtest — comfortably within the batch VPS; no serving-time cost. No LSTM/torch.

## Next
Let the daily capture accumulate ~90 days of Delhi history, then `forecast backtest` yields
the real R7 verdict and the prospective log starts compounding.
