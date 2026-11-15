# M19a — Flood Hub destination slice (access-free) — DONE

Built per [M19-plan.md](M19-plan.md) on the operator's chosen **defaults**
(1a recorded-overlay path, 2a explicit market→zone config, 3a flood-safe reroute exclusion,
4a Book surface + findings). **No external access used, no credentials, no fabrication.**
The live gauge pull (**M19b**) stays access-gated and is handed back to the operator.

## What shipped

- **Destination zone `delhi-yamuna`** (`data/config/destination_zones.csv` +
  `supply/destination_zones.py`): the Yamuna corridor at Delhi (~28.61, 77.29) with the Delhi
  hub markets it covers. Kept **separate from origin belts** (`supply_zones.csv`) so the two
  concepts never blur.
- **Book flood wiring** (`book/service.py`): a lot's intended market → destination zone →
  latest overlay → `FloodFlag` into the (already-tested) decision engine. A reroute into
  another flood-exposed hub is marked **not flood-safe** — the Book never moves stock from
  one flooded destination to another.
- **Access-free overlay path** (`vervana supply floodhub-record`): records a riverine overlay
  from an **official CWC/IMD bulletin** with a **mandatory source URL** and a verified
  severity — nothing invented. Lights the flood-driven REROUTE today; identical in effect to
  a live pull once access lands.
- **Honest surface** (CLI + `/book`): every lot shows a destination flood line — severity +
  source when present, *"access pending — NOT 'no flood risk'"* when mapped but empty, or
  *"not in a mapped flood zone"* otherwise.
- **Tests:** 5 new, fully offline.

## The seam this closed

`service.decide_for_lot` passed `flood=None` with a docstring that literally said *"supply_
zones has no destination zones until M19."* The decision engine's flood path
(`FloodFlag`, flood-driven REROUTE precedence) was built and tested back in M17 — M19a is the
data wiring that finally feeds it. Nothing in the engine changed.

## Real output (dev store)

**Before an overlay — honest "access pending" (NOT "safe"):**
```
$ vervana book decide 3 --horizon 14      # Capsicum @ Azadpur, warehouse near Kullu
  VERDICT: REROUTE
  why: PMY Kullu nets ₹60.00/kg vs best on-hand ₹31.06/kg … materially better landed realisation.
  flood overlay (riverine) delhi-yamuna: Flood Hub access pending — no overlay
    (this is NOT 'no flood risk', just no data).
```

**Operator records an official riverine bulletin (provenance mandatory):**
```
$ vervana supply floodhub-record delhi-yamuna SEVERE \
    --source-url "https://cwc.gov.in/yamuna-bulletin-2026-11-14" --issued 2026-11-14
recorded riverine overlay delhi-yamuna=SEVERE (added=1 updated=0; total in store=1)
riverine-only; a tail-risk overlay, never a price/band feature.
```

**After — the SAME reroute, now flood-driven (the reason changes, not just a badge):**
```
$ vervana book decide 3 --horizon 14
  VERDICT: REROUTE
  why: intended destination zone 'delhi-yamuna' is flood-exposed (SEVERE); PMY Kullu is a
       non-exposed destination at ₹60.00/kg net … — move to cut riverine exposure.
  uncertainties: riverine flood overlay on destination zone 'delhi-yamuna' (SEVERE) —
       tail-risk to logistics, NOT priced in
  invalidated if: the flood overlay on 'delhi-yamuna' clears or worsens (riverine only)
  flood overlay (riverine) delhi-yamuna: SEVERE (issued 2026-11-14;
       Operator-recorded from official riverine bulletin (CWC/IMD)).
```

`/book` renders 200 with the flood-exposed reasoning and the riverine flood line.

### Tests
```
$ uv run pytest tests/test_book_flood.py
5 passed

$ uv run pytest            # full suite
7 failed, 272 passed       # the 7 are the known pre-existing failures (M12); 0 in
                           # book/flood/supply. (267→272: +5 M19a tests)
```
```
$ uvx ruff@0.6.9 check <touched files>
All checks passed!
```

## Honest limitations / deferred

- **M19b (live pull) is blocked on access.** `floodhub-fetch` still raises
  `PartnerAccessPending` and fetches nothing. Going live needs the operator to join the Flood
  Forecasting API waitlist and set `VERVANA_FLOODHUB_API_KEY`; then the gauge-discovery +
  `FloodStatus` field mapping is confirmed against the live schema (audit gap **F2**) before
  the first pull. **No code change is needed at the Book** — a fetched overlay feeds exactly
  the same path a recorded one does.
- **One destination zone** (`delhi-yamuna`) for now. Adding more corridors is a config change.
- **Flood flag is logistics-only**, never a price/band input, and absence always reads as
  "no data", never "safe" — enforced and tested.
- **Acceptance criteria**: all met (riverine-only; access-pending honest and distinct from
  no-risk; recorded overlay requires provenance + valid severity; flood-driven REROUTE
  demonstrated end-to-end; reroute never enters another flooded hub; no migration; offline
  tests; no new regressions; ruff clean).
