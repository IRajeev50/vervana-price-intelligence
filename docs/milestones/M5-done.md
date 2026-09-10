# M5 — Ground-truth study · DONE (interim; upgrades to real on invoices)

- **Status:** COMPLETE as an **interim** study. The machinery is built so that supplying
  trader invoices upgrades it to the **real, date-matched verdict with no code change**.
- **Date:** 2026-09-10. **89 offline tests pass, lint clean.**

## Definition of done vs actual
| Criterion (§5.2) | Result |
|---|---|
| Reference = trader invoices, not Agmarknet | ✅ `invoice` table is the reference; Agmarknet is only a comparator/proxy. Present-mode logic prefers invoices whenever any exist. |
| Median abs % deviation per commodity | ✅ `_deviation` (date-matched) + `_level_deviation` (date-agnostic fallback). |
| Agmarknet a third comparator, never the yardstick | ✅ In REAL mode invoices are the reference; Agmarknet is proxy **only** in interim, loudly labelled (R4). |
| Additional ground-truth sources plug in | ✅ pluggable `PricePoint` sources (`video_points`, `agmarknet_points`, `invoice_points`); add more without touching the study. |
| Reproducible from one command | ✅ `vervana groundtruth report`. |
| RISK verdicts depending on it move from PENDING | ⏳ **Stays PENDING** — honestly. R3/R4 cannot resolve without invoices; the study says so rather than faking a verdict. |

## Real interim output (`vervana groundtruth report`, no invoices yet)
```
mode: INTERIM · reference: agmarknet_national (PROXY) · comparator: video
  commodity        matched days   median abs % dev
  Capsicum                   12            21.2%
  Garlic                     80            36.6%
  Onion                     190            46.4%
  Mango                       6           370.6%
  Pomegranate                10           437.0%
  Potato                    178          1425.4%
  Tomato                    200          1823.1%
  overall median deviation: 370.6%
  ⚠ NO TRADER INVOICES YET — this is NOT the ground-truth verdict.
  ⚠ Basis: LEVEL only (typical video level vs typical Agmarknet level).
  ⚠ Agmarknet is a PROXY (R4), national not Delhi, video unit assumed ₹/kg (R13).
  R3 PENDING — video treated as sentiment, never an executed price, until invoices validate it.
```

## The interim finding (weak, but genuinely useful)
The deviations split sharply: **Onion/Capsicum/Garlic 21–46%**, but **Potato 1425% and
Tomato 1823%.** That is not random — it strongly indicates the video quotes for
**Potato/Tomato are stated in ₹/quintal, not ₹/kg** (e.g. a "1500–1600" tomato quote is
₹/quintal), while Onion/Garlic are quoted per-kg. So the corpus needs **per-commodity unit
normalisation** before it is usable, and the R3/R13 concerns are real, not theoretical.
This is a diagnostic the interim study surfaced — it is **not** the ground-truth verdict.

## How it upgrades when you send invoices
1. `vervana ingest invoices-csv <your_invoices.csv>` (template: `data/samples/invoices_template.csv`
   — columns: commodity, market, date, price_rupees_per_kg, trader, source_ref, notes).
2. `vervana groundtruth report` now runs in **REAL** mode: reference = your invoices,
   MAPD(video vs invoices) per commodity, and the **R3 verdict resolves** — HOLDS if median
   deviation ≤ 10%, FAILS (video = sentiment, not price) if > 10%. Tests already prove both
   branches fire (`test_real_mode_r3_holds`, `test_real_mode_r3_fails`).

## Improving it later (your note)
When invoices arrive we will also: (a) fix the per-commodity unit normalisation the interim
run exposed (Potato/Tomato ₹/quintal → ₹/kg), (b) add date-matched (not just level)
comparison once invoice dates overlap the video window, and (c) bring Agmarknet in as the
documented *third* comparator beside the invoice reference.

## Cost impact
₹0 fixed.

## Honest status
The study is built and runs, but **R3 is unanswered** — by design. It refuses to validate
video against Agmarknet (R4) and waits for real invoices. The interim number (video runs
wildly off national wholesale for Potato/Tomato) is a data-quality flag, not a verdict.
