# M1 — Data model & entity registry · DONE

- **Status:** COMPLETE. Built whole (per your call), model-first then resolution.
- **Date:** 2026-09-10. **Branch:** `m1-data-model`. Gate 1 not required (no data collection).

## Definition of done vs actual

| Criterion (from Part 6) | Result |
|---|---|
| **Source-class guard test passes** (naive "average potato price today" blocked) | ✅ `test_naive_average_across_classes_is_blocked` — a mixed quote+retail set raises `MixedSourceClassError`; class-scoped average works and excludes superseded rows. |
| **200-alias labelled set runs with a reported accuracy figure** | ✅ 198-row set; **lexical 89.9%**, **phonetic 91.4%** accuracy@1 (leave-one-out). Full breakdown below. |
| Schema + migrations | ✅ 8 tables; `alembic upgrade head` / `downgrade base` round-trips (tested). |
| Repository layer + guard | ✅ aggregation only via the repository; append-only (`supersede`, no UPDATE path). |
| Registry seeded from Agmarknet lists | ✅ bootstrap seed: 30 commodities, 20 varieties, 7 Delhi markets, 37 verified official aliases. Full master import deferred to M2. |
| Alias table + fuzzy matcher (two approaches) | ✅ lexical+transliteration and phonetic, both evaluated. |
| Unit-convention table | ✅ present; unknown weight ⇒ canonical price NULL (no 50 kg guess), tested. |
| Review-queue backend (usable interface) | ✅ backend + CLI (`vervana review list/approve/reject`); approve requires a recorded reviewer. |

**44 tests pass, offline. Lint + format clean.**

## Real output (captured this session)

```
$ make test
44 passed in 0.70s

$ vervana registry seed
commodity    30
variety      20
grade         0
market        7
alias        37

$ vervana match eval        # leave-one-out over the 198-row labelled set
Approach: lexical    accuracy@1: 89.9%  (178/198)
    agmarknet_official         100.0%  (30/30)
    hindi_spoken                93.3%  (28/30)
    hinglish_transliteration    94.7%  (71/75)
    qcomm_sku_title             96.8%  (30/31)
    trader_colloquial           59.4%  (19/32)
Approach: phonetic   accuracy@1: 91.4%  (181/198)
    agmarknet_official         100.0%  (30/30)
    hindi_spoken                96.7%  (29/30)
    hinglish_transliteration    98.7%  (74/75)
    qcomm_sku_title             96.8%  (30/31)
    trader_colloquial           56.2%  (18/32)

# review queue, end to end
$ vervana review list
review#1  score=92.0  'aloo' -> commodity#1 [phonetic]
$ vervana review approve 1 --reviewer rajeev
approved: alias#38 'aloo' verified by rajeev
```

## The honest finding from the matcher evaluation

**Phonetic edges out lexical (91.4% vs 89.9%)**, mostly by handling Hinglish spelling drift
better (98.7% vs 94.7%). But the number that matters is the **breakdown, not the headline**:

- Transliteration / Hindi / SKU-title forms resolve at **94–100%** — spelling variants of
  the same word collapse well, which is exactly what normalisation + fuzzy/phonetic
  matching is good at.
- **`trader_colloquial` collapses to ~56–59%.** These are *different words* — regional
  trader terms (kanda, dungri, doodhi, vangi, kobi) with no near neighbour in the index. No
  amount of fuzzy/phonetic scoring turns "kanda" into "onion"; that needs a lexicon or
  embeddings.

**Implication for the product:** entity resolution is a *lexicon-building* problem, not a
string-matching one. The matcher earns its keep on spelling variants and typos; genuinely
new colloquial/regional terms must go through the human review queue and become known
aliases. This is precisely why the registry + review workflow (not the matcher) is the
asset (`R9`), and why the review queue is built as real infrastructure, not an afterthought.

## RISK register

The generator now shows its **first live code tag**: `R9-NOT-IP` at
`src/vervana/models/entities.py:26` (verdict PENDING) — the registry is where the "we own
the dataset" claim is load-bearing, and it is flagged there. `make risks` → 13 risks, 1 code
tag; register regenerates deterministically.

## Deviations / decisions made during the build

- **Enums:** used `Enum(native_enum=False)` (VARCHAR+CHECK on both engines) via an
  `enum_column` helper, and `enum.StrEnum` classes — after an initial `String`-typed version
  returned plain strings and broke `.value`. Portable, avoids Postgres native-ENUM migration
  friction, round-trips as real enums. Two bugs the tests caught: this, and a fixture that
  committed on teardown after a deliberate IntegrityError.
- **Alembic migrations** import `vervana.db.base` (custom `UTCDateTime`); added to the mako
  template so every future migration carries it.
- **200-alias set is a bootstrap** (`data/eval/aliases_200.csv`, 198 rows) from real,
  verifiable naming; SKU-title rows use a realistic format tagged `qcomm_sku_title` and are
  **for your verification** (OPEN_QUESTIONS #… / M1-plan §6.2). It gets replaced/augmented
  from the real corpus at M2/M6.
- **Agmarknet codes left blank** in the seed rather than invented; the M2 import fills real
  codes.

## What M1 deliberately did NOT do
No ingestion (M2), no API/dashboard/WhatsApp (M3), no models (M4), no web review UI (M3, CLI
suffices now), no `ingest_run`/`context_signal`/observer tables (arrive with their consumers),
nothing YouTube-shaped (Gate 1).

## Cost impact
₹0 fixed (all new deps are libraries; embedding/torch path stays deferred). `RUNNING_COSTS.md`
updated.

## Next
M2 — Agmarknet ingest + the Delhi coverage study (`R5`), the first experiment that tests
whether the product has an edge at all. Needs the **data.gov.in API key** (env var). I'll
write `docs/milestones/M2-plan.md` and stop for review.
