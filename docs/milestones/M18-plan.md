# M18 — Capsicum & Onion live experiments — PLAN

Status: **PLAN, awaiting go.** No files change until the forks below are chosen.
Builds on M17 ([The Book](M17-done.md)) and the [M16 audit](M16-audit.md). **No external
access required** — this milestone is access-free and offline-testable.

## Why this milestone

The master brief names Capsicum and Onion as the first two live experiments and gives one
explicit warning: **"verify actual sourcing belts first — don't assume Nashik/Pune
weightings."** M18 is that verification, run end-to-end through the real pipeline
(chain → band → Book) on two commodities with deliberately different supply chains:

- **Onion** — storable rabi crop, months of honest horizon, buffer-stock dynamics.
- **Capsicum** — perishable, honest horizon in weeks, no storage buffer.

The point is not to produce a shippable forecast (it almost certainly won't — see the
honesty note below). The point is to prove the plumbing on real commodities **and to replace
assumed belts with evidenced ones**, carrying provenance the whole way.

## What the audit found (the real starting state)

| Thing | State today | Source |
|---|---|---|
| Onion supply zones | `nashik-onion`, `indore-onion` only | `data/config/supply_zones.csv` |
| Onion profile regions | Maharashtra; Karnataka; Madhya Pradesh | `data/config/crop_profiles.csv` |
| **Karnataka onion belt** | **claimed in profile, no zone** | gap |
| **Capsicum supply zones** | **none at all** | gap |
| Capsicum profile regions | Karnataka; Maharashtra; Himachal Pradesh (unvalidated) | `crop_profiles.csv` |
| Market coordinates | **unpopulated everywhere** (`latitude`/`longitude` nullable, all null) | `models/entities.py:80`, seeds |
| Mandi arrivals **quantity** | **not stored** (capture-change gap) | M16 audit row |
| Band kill-gate | **0/45 commodities shippable** | `data/backtests/band_latest.json` |

Two consequences fall straight out of this:

1. **We cannot weight belts by volume** we do not store. Any belt share must come from
   *which mandis actually report the commodity* (Agmarknet coverage, access-free) and from
   *authoritative external production statistics, cited* — never an invented percentage.
   This is the honest form of "don't assume Nashik/Pune weightings."
2. **The Book will say WAIT on both.** Neither band clears the kill bar, so M17's honesty
   gate forces anchor-fallback WAIT. M18 does **not** paper over that — it demonstrates the
   gate firing correctly on the two flagship commodities, and lights up the parts that *do*
   bite today: the chain narrative, the cost stack, and (newly) REROUTE once belt-mandi
   coordinates exist.

## Honesty note (read before approving)

M18 will **not** make Capsicum or Onion "forecastable." It will:
- correct and extend the belt config from evidence, with provenance on every row;
- populate real coordinates for the belt mandis, which activates sourcing/REROUTE;
- run the full pipeline on both and **report exactly what each stage does and does not yet
  support**, including the WAIT verdicts.

If the plan over-promised a shippable forward price here, it would be the exact overclaim the
brief forbids. It doesn't.

## Scope (default plan — data + wiring, no new model)

1. **Establish belts from evidence, not assumption.**
   - Pull Agmarknet **coverage** for Onion and Capsicum: which markets report each, how
     regularly, over the available window (reuses `analytics/coverage.py`, no new capture).
   - Cross-check the producing regions against **authoritative public production statistics**
     (National Horticulture Board / Ministry of Agriculture horticulture data, or operator-
     supplied figures), **cited by URL/source**. No belt is asserted without a citation.
   - Result is a **belt provenance table** in the findings doc: belt → district → state →
     evidence (coverage + external stat) → confidence. **No volume weights are invented;**
     where real share is unknown we say so.

2. **Correct/extend `supply_zones.csv`.**
   - Add the **Karnataka onion** belt the profile already claims (e.g. Hubballi–Gadag), with
     provenance in `docs/SUPPLY.md`.
   - Add **Capsicum belts** from scratch for the regions evidence supports (Karnataka /
     Himachal / Maharashtra), district-HQ coordinates as the deliberate starting
     approximation (same convention as existing zones — `supply/zones.py` docstring).

3. **Populate belt-mandi coordinates** on the `Market` rows these belts feed (and the
   destination mandis like Azadpur). This is the access-free fix that turns the Book's
   "distance unknown" into a real freight estimate and makes **REROUTE** evaluable for the
   first time. Coordinates are config, provenance-tagged, not invented precision.

4. **Run the pipeline end-to-end on both** and capture **real output**:
   - `intelligence` chain narrative for Onion and Capsicum;
   - `forecast` band + kill decision for each (expected: not shippable → documented);
   - `book decide` on a **sample lot of each** (operator-realistic, clearly marked example),
     showing the WAIT gate and — where belt coords now exist — a live REROUTE candidate.

5. **Write `docs/milestones/M18-done.md`** — the findings report: belt provenance table,
   before/after zone config, the real chain/band/Book output, and an explicit list of what
   is still gated (bands, arrivals volume) and on what milestone it unblocks.

**Migration:** none expected — this is config/data + a findings doc. (Fork 2b would add one.)
**Tests:** belt-config load + coordinate wiring covered offline; no network in tests.

## Decision forks

**Fork 1 — Belt evidence basis** *(how we establish "real belts")*
- **1a (recommended):** Agmarknet coverage + **cited** external production stats; provenance
  on every belt; **no invented volume weights**. Access-free, honest, ships now.
- 1b: Block M18 on the **arrivals capture change** first, so belts can be volume-weighted
  from our own store. Honest but couples this milestone to a schema change and a data-backfill
  wait.
- 1c: Operator supplies belt weightings directly (you hand me the shares); I wire them with
  your attribution as the source.

**Fork 2 — Scope**
- **2a (recommended):** Data + wiring only (zones, profiles, market coords) + findings doc.
  No new model, no migration.
- 2b: Add a first-class **belt-share table/model** (migration) to hold evidenced shares per
  commodity. Heavier; only worth it if 1c/arrivals give real weights to store.

**Fork 3 — Capsicum coverage this milestone**
- **3a (recommended):** Add Capsicum belts + representative mandis from scratch, with
  provenance. Both flagship commodities land together.
- 3b: Onion-only now (fix the Karnataka gap, wire coords), Capsicum deferred to M18b.

**Fork 4 — Validation surface**
- **4a (recommended):** `M18-done.md` findings report only (belt provenance table + real
  chain/band/Book output for both).
- 4b: Also add a `/belts` web view rendering the evidenced belts + coverage per commodity.

## One thing I need from you (governance)

Fork 1a cross-checks belts against **public** horticulture production statistics and cites
them. That means a web fetch of public NHB / Ministry-of-Agriculture pages for citation
(read-only, public data, no scraping of gated sources, nothing personal sent out). If you'd
rather supply the figures yourself (1c) or point me at a specific source, say so — otherwise
I'll cite public horticulture statistics and surface every source in the belt table for your
review before any belt is treated as settled.

## Recommended path

**1a + 2a + 3a + 4a** — access-free, honest, both commodities, evidence-cited belts,
market coords wired (REROUTE goes live), findings reported with the WAIT gate shown working.
No migration, no new model, no overclaim.

Reply with the forks (or "defaults") and I'll build.
