# M17 — The Book (Module F): inventory & margin intelligence — DONE

Built per [M17-plan.md](M17-plan.md) with the operator's chosen **defaults** (1a anchor
fallback, 2a append-only event log, 3a HOLD/RELEASE/WAIT + REROUTE, 4a per-commodity CSV).
Advisory only — nothing executes. Real output below, not asserted.

## What shipped
- **Models** (`models/inventory.py`): `inventory_lot` (immutable purchase facts) + append-only
  `lot_event` log; current status derived from the latest event, never a stored mutable field.
- **Migration** `d4a7f8e63c21` — applies and reverses cleanly (shown below).
- **Cost stack** (`book/costs.py`, pure, integer paise): storage, financing, outbound
  logistics (reused R15 freight estimate), quality loss — every rate a visible assumption
  from `data/config/book_costs.csv`. New risks R16 (carry), R17 (spoilage).
- **Decision engine** (`book/decision.py`, pure): net realisation → HOLD/RELEASE/WAIT/REROUTE
  with the brief's 5 rationale fields (why · evidence · assumptions · uncertainties ·
  invalidated-if). **Honesty gate:** expected sale price uses the band p50 only where the
  commodity cleared the kill bar; otherwise anchor fallback (today held flat) → forced WAIT,
  no confident forward price invented.
- **DB service** (`book/service.py`) + **repository** (`repository/inventory.py`).
- **CLI** `book` group: `add-lot`, `positions`, `decide`, `costs`.
- **Web** `/book` page on the existing design system + a "Commercial" nav group.
- **Tests**: 18 new, fully offline.

## Real output

### Migration applies + reverses
```
Running upgrade c3f9a2d41e85 -> d4a7f8e63c21, add inventory_lot + lot_event (The Book, M17)
inventory_lot cols: id, commodity_id, variety, grade, quantity_kg,
  purchase_price_paise_per_kg, purchase_date, warehouse, warehouse_lat, warehouse_lon,
  intended_market_id, source_ref, notes, created_at
lot_event cols: id, lot_id, kind, quantity_kg, price_paise_per_kg, event_date, note, created_at
Running downgrade d4a7f8e63c21 -> c3f9a2d41e85   # reverses cleanly
```

### CLI end-to-end (against the dev store, real Apple @ Azadpur prices)
```
$ vervana book add-lot Apple --quantity-kg 2000 --price 80 --date 2026-11-01 \
    --warehouse "Sonipat cold store" --market Azadpur --lat 28.99 --lon 77.02
lot #1: 2000 kg Apple @ ₹80.00/kg bought 2026-11-01, aimed at Azadpur

$ vervana book positions
#1    Apple          2000/2000 kg @ ₹80.00/kg  [ACQUIRED] Sonipat cold store

$ vervana book decide 1 --horizon 21
lot #1: Apple @ Azadpur
  2000 kg remaining of 2000 kg
  VERDICT: WAIT
  why: No validated forward price for Apple. On a flat-price assumption, holding 21d
       costs ₹13.15/kg in carry — but we will not issue a HOLD or RELEASE off an
       unvalidated forward price. Decision gated pending a validated band or your
       expected sale price.
  evidence: expected sale ₹135.00/kg (anchor-fallback: 1/2 qualifying mandis beat
            anchor+seasonal with in-window coverage)
  evidence: immediate executable price ₹135.00/kg
  evidence: net if held 21d ₹121.85/kg vs net if sold now ₹135.00/kg
  evidence: carrying cost ₹13.15/kg: storage 6p/kg/day × 21d; financing 12%/yr on
            ₹80.00/kg × 21d; logistics distance unknown — outbound freight not estimated;
            quality 0.4%/day × 21d = 8.4% of ₹135.00/kg
  uncertainties: no validated forward price (band did not clear the kill bar); expected
            price is today's price held FLAT — the hold figure rests entirely on that
            assumption
  invalidated if: Apple's band clears the kill bar (M20 weather features) or you enter an
            expected sale price for this lot
  (advisory only — nothing is executed.)
```
This is the honesty gate working on live data: Apple's band is not shippable, so the Book
refuses a confident HOLD/RELEASE and says exactly why.

### Tests
```
$ uv run pytest tests/test_book_costs.py tests/test_book_decision.py tests/test_inventory_repo.py
18 passed

$ uv run pytest            # full suite
7 failed, 263 passed       # the 7 are the known pre-existing failures (M12); 0 are book/inventory
```
All five verdicts are each forced by a synthetic scenario, incl. the unshippable-band gate:
```
PASSED test_hold_when_validated_band_beats_now_beyond_uncertainty
PASSED test_release_when_selling_now_beats_holding_beyond_uncertainty
PASSED test_wait_when_validated_edge_is_within_band_uncertainty
PASSED test_unshippable_band_forces_wait_and_never_a_confident_forward_price
PASSED test_reroute_when_alternative_destination_is_materially_better
PASSED test_flood_on_destination_reroutes_to_a_safe_alternative
PASSED test_flood_without_safe_alternative_flags_but_does_not_fabricate_a_reroute
PASSED test_every_decision_exposes_all_five_rationale_fields
```

### Lint
```
$ uvx ruff@0.6.9 check <all touched files>
All checks passed!
```

### Web
`/book` renders on the design system with no console errors; the decision card shows the
WAIT verdict and the full four-column rationale. (Screenshot shared in-session.)

## Honest limitations / deferred
- **All commodities WAIT today** by design — no band has cleared the kill bar, so every lot
  gets the anchor-fallback WAIT. The first real HOLD/RELEASE edge arrives with M20
  (WeatherNext features) or when the operator enters an expected sale price. The cost stack,
  spoilage, and REROUTE logic bite now.
- **Destination flood flag is not wired** (`service.decide_for_lot` passes `flood=None`).
  The engine supports and tests it; the data wiring (destination zones + market→zone map)
  lands in **M19**.
- **REROUTE needs market coordinates** to estimate outbound freight; markets without coords
  are never offered as a reroute (distance-unknown, not a guessed zero).
- **Acceptance criteria**: all met (migration reversible; unshippable→anchor WAIT proven, no
  confident forward price; each verdict forced; 5 fields populated; integer paise; offline
  tests; no regressions; ruff clean).
