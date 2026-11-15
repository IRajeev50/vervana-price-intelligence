# M18 — Capsicum & Onion live experiments — DONE

Built per [M18-plan.md](M18-plan.md) on the operator's chosen **defaults**
(1a evidence-cited belts, 2a data+wiring only, 3a both commodities, 4a findings report).
**No external access used.** Advisory only. Real output below, not asserted.

## What shipped

- **Belts, evidence-cited** (`data/config/supply_zones.csv`): added the **Karnataka onion**
  belt the profile already claimed (`gadag-onion`) and **Capsicum's first-ever belts**
  (`kullu-capsicum`, `kolar-capsicum`). Provenance in [SUPPLY.md](../SUPPLY.md#m18).
- **Capsicum profile corrected** (`crop_profiles.csv`): regions reordered to the evidenced
  order (Karnataka protected cultivation → Himachal seasonal supplier → Maharashtra).
- **Market coordinates** (`data/config/market_coords.csv` + `registry.apply_market_coords`
  + `vervana registry market-coords`): 16 belt/destination mandis wired with provenance-
  tagged district-HQ approximations. **This is the access-free fix that activated the Book's
  REROUTE path** (M17 could never reach it — all markets were coordinate-less).
- **Carried-over fix:** `test_risk_generator` still expected 13 declared risks; M17 added
  R16/R17 → 15 but left the assertion stale (failing on `main`). Corrected here.
- **Tests:** 4 new, fully offline.

## The honest headline

**Neither commodity is forecastable yet, and M18 does not pretend otherwise.** The band
kill-gate clears nothing, so the Book's honesty gate (M17) governs both. What M18 *did*
prove on real data: the belts are now evidenced not assumed, and the Book's freight-aware
**REROUTE** works end-to-end.

## Real output (dev store: 3,584 Onion rows, 1,126 Capsicum rows)

### Band kill-gate — both commodities WAIT-gated (honest negative)
```
$ vervana forecast band
series=61  commodities=45  shippable=0
commodity                mandis  pass  ship?
Capsicum                      2     0     no
Onion                         2     1     no
No commodity's band beat the anchor + seasonal with in-window coverage —
serving the labelled baseline band everywhere (honest negative result).
```
Onion passes the walk-forward edge at 1 of 2 mandis but not the full ship bar; Capsicum at
0 of 2. So the Book serves the anchor fallback for both — exactly as designed.

### Coordinates wired
```
$ vervana registry market-coords
coords updated=16 unchanged=0        # idempotent on re-run: updated=0 unchanged=16
```

### The Book — REROUTE now fires (impossible before coordinates)

**Onion** (MP cold store → Indore APMC, 45-day horizon) — a freight-aware cross-belt reroute:
```
$ vervana book decide 4 --horizon 45
lot #4: Onion @ Indore APMC
  VERDICT: REROUTE
  why: SMY Bhuntar nets ₹51.89/kg vs best on-hand ₹36.69/kg
       (executable ₹56.00/kg less freight 411p) — materially better landed realisation.
  evidence: expected sale ₹36.69/kg (anchor-fallback: 1/2 qualifying mandis beat
            anchor+seasonal with in-window coverage)
  evidence: net if held 45d ₹29.50/kg vs net if sold now ₹36.69/kg
  evidence: carrying cost ₹7.19/kg: storage 4p/kg/day × 45d; financing 12%/yr on
            ₹30.00/kg × 45d; logistics reused sourcing freight estimate (R15);
            quality 0.3%/day × 45d = 13.5% of ₹36.69/kg
  (advisory only — nothing is executed.)
```

**Capsicum** (Kullu pack-house → Azadpur, 14-day horizon) — the local HP mandi beats
trucking to Delhi:
```
$ vervana book decide 3 --horizon 14
lot #3: Capsicum @ Azadpur
  VERDICT: REROUTE
  why: PMY Kullu nets ₹60.00/kg vs best on-hand ₹31.06/kg (executable ₹60.00/kg
       less freight 0p) — materially better landed realisation.
  evidence: carrying cost ₹9.63/kg: storage 8p/kg/day × 14d; financing 12%/yr on
            ₹55.00/kg × 14d; quality 1.5%/day × 14d = 21.0% of ₹32.50/kg
  (advisory only — nothing is executed.)
```

**The honesty gate also still fires** where a belt market has no executed print — Onion
aimed at Lasalgaon (no `executed_summary` row there) returns `WAIT: no executable price on
record … decision gated`, never an invented price.

### Tests
```
$ uv run pytest tests/test_market_coords.py
4 passed

$ uv run pytest            # full suite
7 failed, 267 passed       # the 7 are the known pre-existing failures (M12); 0 in
                           # belts/book/registry. (263→267: +4 M18 tests)
```
```
$ uvx ruff@0.6.9 check <touched files>
All checks passed!
```

## Belt provenance (no invented weights)

| Commodity | Belts now in config | Evidence basis |
|---|---|---|
| Onion | Nashik (MH), Indore (MP), **Gadag (KA, new)** | Maharashtra ~42%, MP ~15%, Karnataka ~13–15% national share (NHB); Agmarknet coverage confirms all three observable |
| Capsicum | **Kullu (HP, new)**, **Kolar (KA, new)** | Karnataka leads protected-cultivation capsicum; HP = seasonal Kullu-valley supplier (NHB/CEIC); HP dominates our Capsicum coverage |

Coverage counts are **consumption-skewed** (Tamil Nadu tops raw report counts) so coverage
alone is never treated as a belt — it only confirms observability; production share comes
from the cited statistics. **Mandi arrivals volume is not stored, so no belt share is
claimed.**

## Honest limitations / deferred

- **Both commodities WAIT-gated** — no band clears the kill bar; the first real HOLD/RELEASE
  edge needs M20 (WeatherNext features) or an operator-entered expected sale price.
- **REROUTE has no liquidity filter.** It ranks mandis by net executable price minus
  freight; with arrivals volume unstored, thin hill-market prints can out-rank deep
  production markets (the Onion→SMY Bhuntar reroute above is exactly this shape — a real,
  freight-aware figure, but an HP mandi that mostly *imports* onion). The verdict shows its
  full working; a volume-aware filter unblocks with the **arrivals capture change**.
- **Coordinates are district-HQ approximations**, compounding the R15 freight assumption —
  a REROUTE's rupee figure is only as precise as both. Refining a point is a config change.
- **Maharashtra capsicum** is named in the profile but weakly covered in our data; no zone
  was added without evidence.
- **Acceptance criteria**: all met (belts evidenced + provenance-cited, no invented weights;
  coordinate loader idempotent, skips unknown markets; REROUTE demonstrated live on both
  commodities; WAIT gate demonstrated; integer paise throughout; offline tests; no new
  regressions; ruff clean).
