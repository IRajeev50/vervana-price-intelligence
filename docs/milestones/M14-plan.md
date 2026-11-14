# M14 - Phase 2: weather-aware quantile price band + margin watch - PLAN

- **Status:** PLANNED (2026-11-14). No code until Rajeev's go.
- **Decision applied (option A):** build the band + its kill-test harness on the
  features that exist **today** (price lags, arrivals, seasonality). Weather
  features are a **documented, empty feature group** that drops in the day
  WeatherNext access lands - the backtest is built to report **with-vs-without
  weather** so the weather lift is measurable, never assumed.
- **Working gate (option B):** no regressions vs the 231/238 baseline (7
  pre-existing failures stay documented).

## The one rule, made concrete for a BAND

A band ships **per commodity** only if, on expanding-window walk-forward:
1. its **p50** beats the **anchor (`naive`/last-price)** AND **`seasonal_naive`**
   on **MAE** and **WAPE**; and
2. the band's **realized coverage** lands in the agreed acceptance window
   (Open Q3); and
3. (tie-breaker) at equal coverage the band is **sharper** (narrower mean width)
   than the conformal baseline band.

Where any commodity fails, **serving exposes the baseline + conformal interval,
labelled as such**, and `M14-done.md` records the **negative result** for that
commodity. Given the known anchor dominance (R7) and that **weather is still
absent**, the honest prior is that **few or no commodities beat the anchor in
Phase 2** - that is an acceptable, documented outcome, not a reason to widen the
gate.

## Grounding (read from the repo)

- Baselines exist: `naive` (anchor), `seasonal_naive`, `moving_average`
  (`forecast/baselines.py`), each returning `Forecast(point, low, high)` with a
  +/- z*sigma interval.
- Harness `forecast/backtest.py::walk_forward` is expanding-window, one-step,
  reporting MAE(paise), sMAPE, **directional**, **pi_coverage**, pnl_vs_naive.
  **WAPE is not yet computed** - Phase 2 adds it (the directive names it).
- `forecast/kill.py` gates GB vs seasonal on directional margin (>10%),
  fail-closed from `data/backtests/latest.json`. Current `latest.json`: GB
  directional 0.636 vs seasonal 0.60 -> **GB fails the bar today** (matches "lost
  to the anchor").
- Series: `forecast/series.py::price_series` (daily canonical paise/kg,
  executed_summary). GB features today = price lags t-1..t-7 + day-of-week
  (`models.py`). **Arrivals are not yet a feature.**
- Live RISK tags to respect: **R7** (forecast-bar), **R13** (range-midpoint),
  **R6** (moat-model-gap). Phase 2 adds none of its own data; it reuses these.

## Scope

### 1. Band models (`forecast/band.py`)
- **Conformal baseline band:** wrap `seasonal_naive` (and `naive`) with
  **split-conformal** residual quantiles from the training window -> a calibrated
  p10/p50/p90. This is BOTH the honest band-to-beat AND the labelled fallback
  served when the challenger loses (so it is never wasted work).
- **Quantile challenger:** `HistGradientBoostingRegressor(loss="quantile",
  quantile=q)` fit for q in {0.1, 0.5, 0.9} on the feature matrix below;
  predictions sorted to enforce p10<=p50<=p90 (monotone). Lazy sklearn import,
  same as `models.py`.
- Both return a `Band(p10, p50, p90)`; pure, unit-tested on synthetic series.

### 2. Features (existing now; weather a labelled empty slot)
- `forecast/features.py`: price lags (t-1, t-7), rolling mean/std (7), day-of-week,
  month; **arrivals** lag + arrival-shock (z-score vs trailing mean) from the
  Agmarknet `arrivals` column already stored. A **`weather` feature group** is
  defined but **empty until WeatherNext lands** - wired so the backtest can run
  `with_weather=False` (now) and `True` (later) and report the delta.

### 3. Harness extensions (`forecast/backtest.py`)
- Add **WAPE**. Add a **quantile walk-forward** returning per-series: p50 MAE &
  WAPE & directional, **band coverage** (share of actuals in [p10,p90]), **mean
  band width**. Expanding-window only (no leakage), same discipline as today.

### 4. Kill discipline for the band (`forecast/kill.py` extension)
- New pure `evaluate_band_kill(...)` per commodity: ship iff p50 beats anchor AND
  seasonal on MAE and WAPE, and coverage in the acceptance window. Persist
  per-commodity verdicts to `data/backtests/band_latest.json`; `load_band_decision`
  fail-closed. Serving reads it and shows the challenger band only where it won,
  else the conformal baseline band, **labelled**.

### 5. Scenario labels (scaffolded, weather-gated)
- `rain-crushes-arrivals` and `heat-spike` are **defined** as labelled scenarios
  tied to the weather feature group; they **emit nothing until weather features
  exist** (no fabrication). A naked number is never emitted - each is a labelled
  scenario with its evidence or it does not fire.

### 6. Margin watch (read surface)
- Pure `margin_watch(price_paise, band)` -> {favorable (< p25), in-band, caution
  (> p75)} with the band's provenance. A CLI (`vervana forecast margin-watch
  --commodity --market --price`) and a minimal page showing a price vs its band +
  (Phase 3) the flood overlay slot. Phase 4 feeds GRN lines through this exact
  function.

### 7. Surfaces + docs
- `vervana forecast band` (run the backtest, show the per-commodity table + ship
  verdicts), `margin-watch`. `docs/INTELLIGENCE.md` (band + kill rule + the
  with/without-weather plan), `docs/RISK_REGISTER.md` (note the band inherits R7/
  R13), `RUNNING_COSTS.md` (zero - CPU only).

## Tests (offline, no network)
- Conformal band: on a synthetic AR(1) series, realized coverage of the p10-p90
  interval is within tolerance of nominal (calibration sanity).
- Quantile monotonicity (p10<=p50<=p90) always holds.
- WAPE + band-coverage metrics: exact values on a tiny hand-checked series.
- `evaluate_band_kill`: ship only when p50 beats both baselines AND coverage in
  window; fail-closed with no results file.
- `margin_watch`: boundary cases (exactly p25/p75).
- All 231 currently-passing tests stay green.

## Open questions (genuine forks - need your decision)
1. **Band method:** build **both** (conformal baseline band as the to-beat AND
   the labelled fallback; quantile-GB as challenger) - recommended, nothing
   wasted. OK, or challenger-only?
2. **Granularity + roll-up:** evaluate per **(commodity, mandi)** series where
   history >= `min_train`; decide ship/no-ship **per commodity** by requiring the
   band to beat both baselines on the **majority of that commodity's qualifying
   mandis** (and never ship a commodity with too little history). Agree, or do you
   want strict per-(commodity,mandi) serving?
3. **The p10/p90-vs-"90% coverage" tension (important):** p10/p50/p90 makes an
   **80% nominal** interval (p10-p90), but the directive says *"90% band
   coverage."* Pick one:
   - **(3a)** keep p10/p50/p90 and set the acceptance window to realized
     **[75%, 88%]** (centered on the 80% nominal) - recommended, matches the
     percentiles you named; or
   - **(3b)** widen the band to **p5/p50/p95** and target realized **[85%, 95%]**
     for a true ~90% interval.
   Which?
4. **ToU / weather:** unchanged - Phase 2 uses **no** WeatherNext data (it is not
   granted), so the commercial real-time ToU question does not bind yet; it
   returns when weather features are switched on post-approval.

## Explicitly out of scope (Phase 2)
- Any use of WeatherNext data (access pending) - weather is a wired-but-empty
  feature group; the with-weather backtest runs post-approval.
- Flood Hub (Phase 3), GRN import (Phase 4).
- Changing the existing GB/SARIMA point models or their kill rule (the band kill
  is additive, beside the existing one).
- Fixing the 7 pre-existing failures or the ruff backlog (option B: deferred).
