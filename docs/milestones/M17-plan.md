# M17 — The Book (Module F): inventory & margin intelligence, advisory-only

**Goal.** Build the commercial decision layer: given real inventory lots sitting in a
warehouse, compute expected **net realisation** of holding vs selling now, and emit an
**advisory** BUY / HOLD / RELEASE / WAIT / REROUTE recommendation — every one of which
shows its evidence, assumptions, and what would invalidate it. Nothing auto-executes.

**Why now.** Highest commercial value in the brief, needs **no external access**, and every
upstream input it consumes already exists: the quantile band (`forecast/band.py`), the kill
gate (`forecast/kill.py::load_band_decision`), margin zones (`forecast/margin.py`),
landed-cost ranking (`repository/sourcing.py::landed_cost_ranking`), the flood overlay
(`repository/flood_overlay.py`), and the paise money policy (`money.py`).

---

## 1. Scope

**In scope**
- `inventory_lot` — the immutable purchase facts of one physical lot.
- `lot_event` — append-only status log (so a lot's life is auditable, never silently mutated).
- Cost stack (per lot, per day): storage, financing, outbound logistics, quality loss —
  every rate a **visible assumption** (`RISK` tag), never a quoted cost.
- Net-realisation engine + the five-way advisory decision with the 5-part rationale the
  brief requires.
- CLI `book` group + a `/book` web page on the existing design system.
- Offline tests with synthetic lots and synthetic bands.

**Explicitly out of scope (deferred, stated honestly)**
- **Full BUY origination** — a buy signal is a *procurement* decision (a price below band in
  a sourcing mandi), not a lot decision. M17 surfaces BUY only via the existing
  `margin_watch` zone on a commodity; full BUY lands in the later Procurement Control Centre
  milestone. (See §3, decision 3.)
- **Warehouse flood exposure** — needs a warehouse entity with coordinates and live Flood
  Hub access (audit gap F5). M17 carries warehouse as a label + optional coords on the lot;
  the destination/corridor flood tie-in waits for M19.
- **Auto-execution / order placement** — never. Advisory only, per the brief.

---

## 2. Design

### 2.1 Data model (new)
`src/vervana/models/inventory.py`, migration `*_add_inventory_lot.py` (follows the
append-only + `UTCDateTime` + integer-paise conventions in `db/base.py`).

**`inventory_lot`** — immutable purchase facts:
| column | type | note |
|---|---|---|
| id | pk | |
| commodity_id | FK commodity | ties to the registry (so band/margin can be looked up) |
| variety / grade | str, optional | never invented |
| quantity_kg | Numeric | the physical quantity bought |
| purchase_price_paise_per_kg | BigInteger | integer paise, exact |
| purchase_date | Date | |
| warehouse | str | label (coords optional, see below) |
| warehouse_lat / warehouse_lon | float, optional | for outbound-logistics distance reuse |
| intended_market_id | FK market, optional | the destination the lot is aimed at (for REROUTE) |
| source_ref / notes | str, optional | provenance |
| created_at | UTCDateTime | |

**`lot_event`** — append-only status log (current status = latest event; the lot row is
never rewritten):
| column | type | note |
|---|---|---|
| id | pk | |
| lot_id | FK inventory_lot | |
| event | enum | `ACQUIRED` \| `HELD` \| `RELEASED` \| `WRITTEN_OFF` |
| quantity_kg | Numeric, optional | partial release supported |
| price_paise_per_kg | BigInteger, optional | realised price on RELEASE |
| event_date | Date | |
| note | str, optional | |
| created_at | UTCDateTime | |

Both tables are **empty until the user enters real lots** — like `invoice`, never seeded
with fabricated inventory.

### 2.2 Cost stack — `src/vervana/book/costs.py` (pure, paise)
Per-commodity rates live in `data/config/book_costs.csv` (same pattern as
`supply_zones.csv`), each row a labelled assumption:

```
commodity,storage_paise_per_kg_per_day,financing_annual_pct,spoilage_pct_per_day
```

- **Storage** = `storage_rate × days_held × quantity`.
- **Financing** = `purchase_value × financing_annual_pct × days/365`. Reuses the idea
  behind `config.freight_rate_per_tonne_km` — a single visible rate, `RISK`-tagged.
- **Outbound logistics** = reuse the existing freight estimate (`geo.haversine_km` ×
  `config.freight_rate_per_tonne_km`, `RISK[R15-FREIGHT-ASSUMPTION]`) from warehouse coords
  to the destination market; `None`/"distance unknown" when coords are missing (never guessed).
- **Quality loss** = `spoilage_pct_per_day × days` applied to sellable quantity, valued at
  the expected sale price. A `RISK[R17-SPOILAGE-ASSUMPTION]` constant, never a measured rate.

Every cost returns integer paise and is shown **with its rate visible**, always as an
ESTIMATE. New risk entries: `R16-STORAGE/FINANCE-ASSUMPTION`, `R17-SPOILAGE-ASSUMPTION`.

### 2.3 Net realisation + decision — `src/vervana/book/decision.py`
```
NetRealisation(hold_to_horizon H) =
    ExpectedSalePrice(H) − storage − financing − outbound_logistics − quality_loss
```

**Expected sale price — the crux honesty gate.** Sourced in this strict order:
1. The forecast **band p50** (with p10/p90 as the uncertainty) **only where that commodity's
   band cleared the kill bar** (`load_band_decision(commodity).shippable`).
2. Otherwise — which today is **all 45 commodities** — fall back to the **last-price anchor**,
   labelled "no validated forward price; using today's price held flat", and bias the
   decision toward **WAIT**. The Book **must not invent a confident forward price** where the
   band failed; it inherits `RISK[R7-FORECAST-BAR]`/R13 and does not escape them.

**Immediate-sale alternative** = today's executable price (latest wholesale observation for
the lot's commodity-market, or a user-supplied buyer quote) minus outbound logistics only.

**The five-way advisory** (compare hold-to-H net realisation vs immediate sale, with an
uncertainty margin derived from band width):
| verdict | trigger |
|---|---|
| **HOLD** | expected hold net realisation exceeds immediate sale by **more than** the uncertainty margin |
| **RELEASE** | immediate sale ≥ expected hold realisation, OR spoilage/flood risk argues to move now |
| **WAIT** | the difference is **within** the uncertainty margin — "insufficient edge, no action" (the honest default when the band is unshippable) |
| **REROUTE** | `landed_cost_ranking` shows a destination with materially better landed realisation than the intended market, OR the intended destination carries a Flood Hub riverine overlay (tail-risk flag, never a price input) |
| **BUY** | surfaced only via `margin_watch` on the commodity (below-band/favorable) — see out-of-scope note |

**Every recommendation carries the brief's 5 fields** (mirrors the chain's provenance ethos):
`why` · `evidence` (which data, with links to observations/band/overlay) · `assumptions`
(the exact rates used) · `uncertainties` (band width, unshippable-band fallback, cost
estimates) · `invalidated_if` (a new price print, a flood overlay clearing, a rate change).

### 2.4 Repository / CLI / Web
- `repository/inventory.py` — add lot, append event, current positions (lot + latest status),
  days held.
- CLI `book` group: `book add-lot`, `book positions`, `book decide <lot_id> [--horizon N]`,
  `book costs` (print the rate table).
- `/book` page: positions table + per-lot decision card, reusing the design system in
  `web/templates/base.html` (new nav link under a new **"The Book"** group). Empty-state
  points to `book add-lot`, consistent with the other pages.

---

## 3. Decisions I need from you (genuine forks)

1. **Expected-sale-price fallback when the band is unshippable (today: all commodities).**
   **(a)** last-price anchor held flat, WAIT-biased, clearly labelled *(recommended — honest,
   ships now)*; **(b)** require a user-entered expected sale price per lot; **(c)** both — band
   where it ships, else user-entered if present, else anchor.
2. **Lot status model.** **(a)** immutable `inventory_lot` + append-only `lot_event` log
   *(recommended — auditable, matches the project's append-only ethos)*; **(b)** mutable lot
   row with a status column only (simpler, less audit trail).
3. **Decision breadth in M17.** **(a)** HOLD/RELEASE/WAIT fully + REROUTE via landed-cost;
   BUY surfaced via existing margin-watch only *(recommended)*; **(b)** all five fully,
   including BUY origination now (pulls procurement scope forward).
4. **Cost rates location.** **(a)** `data/config/book_costs.csv` per-commodity, labelled
   assumptions *(recommended — matches `supply_zones.csv`)*; **(b)** global defaults in
   `config.py` only.

---

## 4. Acceptance criteria (gate — real output, no fabricated wins)
- Migration applies cleanly and reverses; `verify_persistence.sh`-style round-trip passes.
- A synthetic lot whose commodity has an **unshippable** band produces a decision that uses
  the **anchor fallback**, is **labelled as such**, and is **WAIT-biased** — proven by test,
  not asserted. **No confident forward price appears for an unshippable band.**
- Each of HOLD / RELEASE / WAIT / REROUTE is produced by a synthetic scenario that forces it.
- Every decision object exposes all 5 rationale fields, populated.
- All cost figures are integer paise; every rate is visible in the output.
- Tests are fully offline (synthetic lots + synthetic bands/overlays); no network.
- No regression: the 226/233 baseline is unchanged (7 known pre-existing failures only).
- `uvx ruff@0.6.9` clean on the touched files.

## 5. Cost
₹0 incremental — no external API, no paid service. Pure compute on data already in the store.

## 6. Test plan (will show REAL output in M17-done.md)
`tests/test_book_costs.py` (cost stack, paise, visible rates), `tests/test_book_decision.py`
(the five branches + the unshippable-band fallback + the 5 rationale fields),
`tests/test_inventory_repo.py` (lot + append-only event round-trip, partial release).

---

**No code until you pick 1–4 (or say "defaults").** On your go I build the migration +
models first, prove persistence, then costs → decision → CLI → web, with real test output in
`M17-done.md`, then PR.
