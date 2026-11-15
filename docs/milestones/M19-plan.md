# M19 — Flood Hub go-live — PLAN

Status: **PLAN, awaiting go.** No files change until the forks below are chosen.
Builds on [M15](M16-audit.md) (the Flood Hub seam) and [M17](M17-done.md)/[M18](M18-done.md)
(the Book's flood-driven REROUTE, already built and tested but not yet wired).

## The access reality (read first — this is a STAGE-4 stop-for-approval item)

Flood Hub's gauge data is **waitlist + API-key gated and NOT granted**. Until
`VERVANA_FLOODHUB_API_KEY` is set, `FloodHubClient.fetch_overlays` raises
`PartnerAccessPending` and **nothing is fetched or fabricated** — by design. I cannot pull
real overlays, and I will not invent them.

So "go-live" splits cleanly into two parts, and only one is buildable today:

- **M19a — the access-free destination slice (build now).** Everything except the live
  gauge pull: the `delhi-yamuna` destination zone, the market→zone map, the Book service
  wiring that turns a destination's flood overlay into a verdict, flood-safe marking on
  reroutes, the destination flood line on the Book, and fixtures/tests. This is exactly the
  slice the M16 audit flagged as *"can ship now, access-free, fixture-tested."*
- **M19b — the live pull (held for your approval).** Set the key, confirm gauge discovery
  (`SearchGaugesByArea`) + `FloodStatus` field mapping against the live schema (audit gap
  **F2**), do the first real overlay pull, go-live. **This needs you to join the Flood
  Forecasting API waitlist and provide the key** — I'll stop here until you do.

M19a makes the Book's flood path **real the instant an overlay row exists** (whether from
M19b's live pull or a provenance-tagged recorded overlay). Zero further code at go-live.

## What's already built (so M19a is wiring, not invention)

- **`decision.py`** fully implements the flood path: `FloodFlag`, flood-driven REROUTE as
  precedence #1 (move off a flood-exposed destination to a `flood_safe` alternative), and
  the flag-without-safe-reroute case (surfaced, never fabricates a reroute). All offline-
  tested since M17.
- **`service.decide_for_lot` passes `flood=None`** — its own docstring says *"supply_zones
  has no destination zones until M19."* This is the one seam M19a closes.
- **`flood_overlay` table + repo** (`record_overlays`, `latest_overlay_for_zone`) and the
  **belt overlay line** (`_flood_overlay_lines`, origin-belt, access-pending honest) already
  exist. M19a adds the *destination* side.

## Scope — M19a (default plan: config + wiring, no migration)

1. **Destination zone `delhi-yamuna`** (`data/config/destination_zones.csv`, new) —
   zone, name, lat/lon (~28.61, 77.29, the Yamuna corridor at Delhi), and the gauge
   search-area hint for when access lands. Kept **separate from `supply_zones.csv`** so
   origin belts (which carry commodities) and destination zones (which don't) stay distinct
   and the belt-overlay logic is untouched.

2. **Market→zone map** — the Delhi destination mandis (Azadpur + the other Delhi markets)
   map to `delhi-yamuna`. Config in the same file (a `markets` column) or a small mapping
   table; **explicit, not proximity-guessed.**

3. **Wire the Book's destination flood flag** — `service.decide_for_lot`:
   - resolve the lot's intended market → destination zone;
   - `latest_overlay_for_zone(session, zone)` → build a `FloodFlag` (or `None` if no overlay
     / access pending);
   - pass it into `decide(...)` (the engine already does the rest);
   - mark a reroute candidate `flood_safe=False` when **its** market maps to a
     flood-exposed destination zone, so a reroute never moves into another flooded hub.

4. **Surface it honestly** — the Book page + `book decide` show a **destination flood line**:
   the overlay severity when present, or *"flood overlay (riverine): access pending — NOT
   'no flood risk', just no data"* when not. Riverine-only label everywhere.

5. **Make the path demonstrable offline** — a seeded overlay-row fixture drives the flood-
   REROUTE end-to-end in tests (no network). See Fork 1 for whether we also add an operator
   **recorded-overlay** CLI so a manually-sourced, provenance-tagged overlay can light the
   path before API access.

6. **`docs/milestones/M19-done.md`** — real output: the flood-driven REROUTE firing on a
   seeded `delhi-yamuna` overlay, the access-pending line when absent, and an explicit
   "M19b blocked on access" note.

**Migration:** none (destination zones are config; `flood_overlay` already exists).
**Tests:** destination zone + map load, flood-flag wiring, flood-safe reroute exclusion,
and the access-pending honest line — all offline.

## Honesty constraints (non-negotiable, carried from M15)

- **Riverine only.** Never rainfall, never urban waterlogging, never crop stress. Labelled
  riverine everywhere it appears.
- **Never a price/band feature.** The flood flag affects REROUTE/RELEASE *logistics*
  reasoning only, never an expected price or a forecast input.
- **Access-pending ≠ no risk.** Absence of an overlay reads as "no data," never "safe."
- **No fabricated overlay.** Data comes only from the live API (M19b) or a provenance-tagged
  recorded overlay (Fork 1a) — never invented, never a guessed severity.

## Decision forks

**Fork 1 — How the path is demonstrable before API access**
- **1a (recommended):** Seam + a provenance-tagged **recorded-overlay** path
  (`supply floodhub-record` CLI: operator logs an overlay from an official CWC/IMD bulletin
  with `source`/`source_url`, exactly as the model already requires). The flood-REROUTE is
  demonstrable offline today and live the moment access lands. Nothing invented.
- 1b: Pure seam — wire it, but it stays dormant ("access pending") until M19b. Honest, but
  the decision path can't be shown on real data until the key exists.

**Fork 2 — Market→destination-zone mapping**
- **2a (recommended):** Explicit config (`destination_zones.csv` with a `markets` column).
- 2b: Proximity inference (market within N km of the zone centroid). Less explicit, and a
  guessed mapping is exactly the kind of implicit assumption the platform avoids.

**Fork 3 — Reroute flood-safety**
- **3a (recommended):** Mark a reroute `flood_safe=False` when its market maps to a
  flood-exposed destination zone — never reroute into another flooded hub.
- 3b: Treat all reroutes as flood-safe for now (weaker; can surface a bad reroute).

**Fork 4 — Surface**
- **4a (recommended):** Book per-lot destination flood line (CLI + page) + findings doc.
  The existing commodity-level belt line on margin-watch stays as-is.
- 4b: Also add the destination line to margin-watch (commodity-level, less precise than the
  lot-level Book view).

## Recommended path

**1a + 2a + 3a + 4a** — build the full access-free destination slice: `delhi-yamuna` zone,
explicit market map, Book flood-flag wiring, flood-safe reroute exclusion, honest access-
pending line, demonstrable offline via a provenance-tagged recorded overlay, findings
reported. **No migration, no credentials, no fabrication.** Then **stop** and hand M19b
(the live key + schema confirmation + first pull) back to you.

## What I need from you for M19b (not M19a)

To take Flood Hub truly live: join the **Flood Forecasting API** waitlist, and once approved,
provide `VERVANA_FLOODHUB_API_KEY`. I'll then confirm the gauge-discovery + `FloodStatus`
field mapping against the live schema before the first pull. Until then M19a stands on its
own and nothing about it is blocked.

Reply with the forks (or "defaults") and I'll build M19a.
