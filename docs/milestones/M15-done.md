# M15 - Phase 3: Flood Hub riverine risk overlay - DONE

- **Status:** DONE (2026-11-14). Branch `m15-phase3-floodhub-overlay`.
- **Decisions applied:** not approved -> **access-pending seam**; **belt-only**;
  gauges discovered **by area** (no hardcoded IDs).
- **Gate (option B):** no regressions vs the 239/246 baseline. Met - 245 passed,
  the identical pre-existing 7 failed.

## The boundary this phase enforces

Flood Hub is **riverine flooding only** - NOT rainfall, NOT waterlogging, NOT crop
stress. It is a **tail-event overlay, never a band/price feature**, labelled
riverine-only on every surface.

## What was built (files)

- `supply/floodhub.py` - `FloodHubClient(PartnerFeed)` gated on
  `VERVANA_FLOODHUB_API_KEY`; pure `overlay_from_statuses()` reducing a zone's
  gauges to its WORST modelled severity using the **verified `Severity` enum**
  (`EXTREME > SEVERE > ABOVE_NORMAL > NO_FLOODING`; `UNKNOWN`/no-model ignored,
  never "no flooding"). Live gauge discovery (`SearchGaugesByArea` ->
  `QueryGaugeForecasts`) is inert until the key lands - field mapping confirmed on
  first access, not guessed.
- `models/flood_overlay.py` + migration `c3f9a2d41e85` (head now
  `c3f9a2d41e85`) - append-only `flood_overlay` (its own table), idempotent on
  (zone, issued_time).
- `repository/flood_overlay.py` - record + latest-per-zone.
- `supply/feeds.py` - Flood Hub listed in `supply status` / `/intelligence`.
- `cli.py` - `vervana supply floodhub-fetch`; **margin-watch now carries a
  riverine overlay line** for a commodity's origin belts.
- `config.py`, `.env.example` - `VERVANA_FLOODHUB_API_KEY`.
- `docs/SUPPLY.md`, `docs/RUNNING_COSTS.md`. Tests: `tests/test_floodhub.py` (6).

## API re-verification (ground rule 4)

Verified against the official RPC docs (floodforecasting.v1): host
`floodforecasting.googleapis.com/v1`; methods `SearchGaugesByArea`,
`QueryGaugeForecasts`; `FloodStatus.severity` enum
`EXTREME|SEVERE|ABOVE_NORMAL|NO_FLOODING|UNKNOWN`; `ForecastTrend`
`RISE|FALL|NO_CHANGE`. The real names let the severity mapping be written without
guessing; the live request stays inert until the key exists.

## Real output

```
$ uv run vervana supply status
[SCAFFOLD] Google Flood Hub - riverine flood overlay
           state: scaffold - access pending (waitlist) ...
           emits: flood_risk_riverine overlay (tail-risk, NOT a band feature, NOT rainfall)

$ uv run vervana supply floodhub-fetch
... No request was made and no data was fabricated. nothing was fetched and nothing was faked. (riverine-only overlay)   # exit 0

$ uv run vervana forecast margin-watch Onion Azadpur --price 25
Onion @ Azadpur — serving: baseline band (conformal) — challenger not shippable
[BELOW-BAND] ₹25.00/kg is BELOW the band — unusually cheap, verify (band p10 ₹33.59 / p50 ₹34.99 / p90 ₹35.98).
flood overlay (riverine): Flood Hub access pending — no overlay available (this is NOT 'no flood risk', just no data).
```
Migration applied: `migrated to head` -> `c3f9a2d41e85 (head)`.

## Test results

- **245 passed, 7 failed, 252 total.** +6 new floodhub tests, all green. The 7
  failures are the identical pre-existing set. **Zero regressions.**
- `ruff@0.6.9` clean on every file this phase added/touched.

## What did NOT work / honest notes

- **No live overlays** - by design (access pending). The severity reduction is
  proven on fixtures; the live gauge discovery is inert and fabricates nothing.
- The margin-watch overlay is **explicit about access-pending** so silence is
  never read as "no flood risk".
- **Belt-only** - transport corridors (belt->Delhi) are a deliberate follow-up
  once belt overlays run live.

## Cost impact

₹0 - free API, scaffold makes no requests. Under the ₹25k ceiling.

## Next step

Open the Phase 3 PR. On merge, **Phase 4 (GRN ground truth + margin watch over
real lines)** - import the Lalit/Vervana GRN exports (local, never committed),
alias GRN commodities into the registry, run the proprietary **origin-belt weather
vs per-line QC rejection** test, and feed real GRN lines through the Phase-2
margin watch + the Phase-3 flood overlay. Note the known data quirks to surface
(Lalit fresh-fruit GRNs stop after Jul 2026; Vervana GRNs show zero recorded
payment) - flag, do not paper over.
