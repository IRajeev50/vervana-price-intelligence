# M1 — Data model & entity registry · PLAN

- **Status:** PLAN (awaiting review). **Depends on:** M0 (done). Gate 1 not required
  (no data collection). **Blocks:** M2 (ingest needs the schema + registry).
- **Two definition-of-done criteria (from Part 6):**
  1. the **source-class guard** test passes (a naive "average potato price today" is blocked);
  2. the **200-alias** labelled set runs with a **reported accuracy figure**.

Because those two criteria are almost independent, and M1 is large, I **recommend
splitting it** (see §7). The plan below is written so it can ship as one milestone or as
M1a + M1b.

---

## 1. What M1 builds (mapped to Part 3)

### 1.1 The fact table — `price_observation` (Part 3.1)
Schema + constraints only in M1; **real rows arrive in M2**. Built now because the
source-class guard and its test need the table to exist.

Columns (names are my call; money is integer paise, time is tz-aware UTC):
- `id`, `commodity_id`, `variety_id?`, `grade_id?`, `market_id`
- **`source_class`** — enum, exactly four: `quote_indicative`, `executed_summary`,
  `executed_trade`, `retail_offer`. Enforced by a SQLAlchemy `Enum` (native ENUM on
  Postgres, `VARCHAR + CHECK` on SQLite) so it holds on both engines.
- **Ranges, never collapsed:** `price_low_paise` (NOT NULL), `price_high_paise` (NOT
  NULL), `price_point_paise` (NULL unless the source gave one number). CHECK
  `price_low_paise <= price_high_paise`.
- **Unit:** `unit_raw` (immutable text, NOT NULL), plus derived
  `canonical_price_paise_per_kg` (NULL when weight unknown), `unit_kg_equivalent`
  (Numeric, not float), `unit_conversion_confidence` (Numeric 0–1). Storing the *factor
  used*, not just the result (Part 3.3).
- **Provenance as a constraint:** `source_url` NOT NULL + non-empty; `raw_quote` NOT NULL
  + non-empty (or `raw_payload` JSON for API rows). A row that can't be traced fails
  insertion.
- **Time:** `observed_at` (tz-aware UTC, NOT NULL); **`time_basis`** enum: `exact`,
  `estimated_window`, `single_daily_quote`, `daily_summary`. For `estimated_window`,
  `observed_window_start/end`. An estimated timestamp is never stored as if `exact`.
- **Append-only:** `supersedes_id` (self-FK, NULL), `supersede_reason`, `created_at`.
  Corrections **insert a new row**; the repository exposes no UPDATE path for prices.
- `observer_id?` (FK, nullable) — reserved for M7 field observers; NULL for public sources.

### 1.2 Entity registry (Part 3.2) — the most valuable component (R9)
- `commodity(id, canonical_name, agmarknet_commodity_code?, notes)`
- `variety(id, commodity_id, canonical_name, agmarknet_variety_code?, notes)`
- `grade(id, commodity_id?, canonical_name, notes)`
- `market(id, canonical_name, apmc_name?, city, state, agmarknet_market_code?, lat?, lon?)`
- **`alias`** exactly per spec: `alias_text, alias_language, alias_source_type,
  canonical_type, canonical_id, confidence, created_by, verified_by, verified_at, notes`.
  - `alias_source_type` ∈ {`agmarknet_official`, `hindi_spoken`,
    `hinglish_transliteration`, `qcomm_sku_title`, `trader_colloquial`}.
  - **Many-to-many is allowed:** no unique constraint on `alias_text`; the same text may
    map to multiple canonicals (e.g. "mirchi" → chilli *or* capsicum) each with its own
    confidence and review state. One variety ↔ many aliases ↔ many SKU titles.
  - `canonical_type`/`canonical_id` is a polymorphic pointer to commodity/variety/grade/
    market (validated in the repository, since cross-table FKs can't be a single DB FK).

### 1.3 Bag-weight lookup (Part 3.3)
- `unit_convention(id, market_id?, commodity_id?, unit_raw, kg_equivalent Numeric,
  source, confidence, effective_from, effective_to)`. **Never hardcode 50 kg.** If no row
  matches, `canonical_price_paise_per_kg` stays NULL and `unit_raw` is preserved.

### 1.4 Review queue (Part 3.2)
- `alias_review(id, alias_id, status[pending|approved|rejected], proposed_by,
  proposed_at, decided_by, decided_at, method, score, notes)`.
- Automated matches enter as **unverified/pending**; promotion to verified requires a
  **recorded reviewer** (sets `alias.verified_by/verified_at`). Built as a **usable CLI**
  in M1 (`vervana review list|show|approve|reject`), not a hand-edited table; the web UI
  comes with M3.

### 1.5 Repository layer + the source-class guard (Part 3.1) — the crux
- A repository is the **sanctioned access path**; the guard lives here (the spec asks for
  a *repository-layer* guard).
- `average_price(...)` and any aggregate **require an explicit `source_class`** and
  **exclude superseded rows** (`supersedes_id` chain) and rows without a canonical unit.
  There is **no** method that averages across classes. Passing a mixed-class set raises
  `MixedSourceClassError`.
- Append-only enforced here: prices are insert-only; a `supersede(old_id, new_row,
  reason)` helper creates the replacement row.

### 1.6 Fuzzy matcher + evaluation (Part 3.2) — two approaches, reported accuracy
- **Approach A — lexical/transliteration:** normalise (NFC, lowercase, strip),
  transliterate Devanagari→roman (`indic-transliteration`), collapse common variant
  spellings, then `rapidfuzz` scoring against the alias index. Returns ranked candidates
  with scores.
- **Approach B — phonetic:** transliterate, then a phonetic key (`jellyfish`
  metaphone/soundex family) with a `rapidfuzz` tiebreak — catches "Shimla Mirchi" ↔
  "shimla mirch" ↔ "capsicum" where spelling diverges but sound/meaning aligns.
- **Evaluation harness:** run both against the 200-alias labelled set; report
  **accuracy@1, precision/recall, and a confusion sample**, side by side, per approach.
- **Embeddings (torch) deliberately deferred** as a heavier third option — only if A and
  B miss the bar — to respect the ₹25k ceiling (ADR). Flagged, not built.

### 1.7 Migrations & seeding
- **Alembic** migrations; `alembic upgrade head` works on SQLite (tests) and Postgres
  (compose). A downgrade is provided.
- **Registry seeded** from an Agmarknet commodity/variety list — *source is an open
  question, see §6.1.*

### 1.8 RISK tags that will appear in M1 code (the register will show them)
- **`R9-NOT-IP`** at the entity-registry/alias-verification module — this is the *only*
  component with a colourable IP claim, and only because of the editorial judgment in
  verification. Verdict: PENDING. (This makes the register show its first live code tag —
  proof the risk system works end-to-end.)
- No other R-tag is load-bearing in M1: R3/R13 land at modelling (M4/M5), R11 at observers
  (M7), R2 at serving (M3). I won't tag where the assumption isn't actually being made.

## 2. New dependencies (all lightweight — no torch, within the cost ceiling)
`sqlalchemy>=2.0`, `alembic`, `rapidfuzz`, `indic-transliteration`, `jellyfish`. For
Postgres at runtime: `psycopg[binary]` (tests stay on SQLite and need no driver).

## 3. Files I plan to create
- `src/vervana/db/__init__.py`, `engine.py` (engine/session from `settings.database_url`),
  `base.py` (SQLAlchemy declarative base + shared types).
- `src/vervana/models/` — `entities.py` (commodity/variety/grade/market/alias),
  `observations.py` (price_observation), `units.py` (unit_convention), `review.py`.
- `src/vervana/repository/` — `prices.py` (incl. the guard + `MixedSourceClassError`),
  `registry.py`, `review.py`.
- `src/vervana/matching/` — `normalize.py`, `lexical.py` (Approach A), `phonetic.py`
  (Approach B), `evaluate.py` (the harness).
- `src/vervana/cli.py` — add `db upgrade`, `registry seed`, `review …`, `match eval`.
- `migrations/` — Alembic env + the initial revision.
- `data/seed/commodities.csv`, `varieties.csv`, `markets_delhi.csv` — the registry seed
  (§6.1).
- `data/eval/aliases_200.csv` — the labelled alias set (§6.2), **for founder verification**.
- Tests under `tests/` (see §4).
- Update `docs/DATA_DICTIONARY.md` (every table/column incl. "must never be used for"),
  `docs/RUNNING_COSTS.md` (M1 deps = ₹0 fixed), and regenerate `docs/RISK_REGISTER.md`.

## 4. Tests that will prove M1 works (real output shown at done-time)
1. **Source-class guard (the headline test):** insert a wholesale `quote_indicative` and a
   `retail_offer` for potato on the same day → a naive "average potato price today" is
   **blocked** (`MixedSourceClassError`); a class-scoped average **works** and **excludes**
   a superseded row. This is the M1 DoD #1.
2. **Provenance constraint:** inserting a `price_observation` with empty/missing
   `source_url` or `raw_quote` **fails**.
3. **Ranges:** `price_low > price_high` rejected; `price_point` may be NULL; range stored
   uncollapsed.
4. **Append-only:** a correction creates a new row with `supersedes_id`; the repository has
   no price-UPDATE path.
5. **Unit unknown → canonical NULL:** no `unit_convention` match ⇒ `canonical_*` NULL,
   `unit_raw` preserved (no 50 kg guess).
6. **Time policy:** naive `observed_at` rejected; `time_basis` required; estimated rows are
   distinguishable from exact.
7. **Registry seed:** `registry seed` loads N commodities/varieties/markets from the seed
   files; counts reported.
8. **Alias many-to-many:** the same `alias_text` maps to two canonicals without error.
9. **Matcher accuracy (DoD #2):** `match eval` runs the 200-alias set and prints
   **accuracy@1 for Approach A and B**, side by side. (Test asserts the harness runs and
   emits a number; the number itself is reported, not hard-thresholded, since the
   bootstrap set is indicative — see §6.2.)
10. **Review queue:** an automated match is enqueued **pending**; `approve` requires a
    reviewer id and sets `verified_by/verified_at`; `reject` records the decision.
11. **Migrations:** `alembic upgrade head` then `downgrade base` round-trips on SQLite.
All offline; Postgres-specific behaviour (native enum) checked in an **opt-in** integration
test that only runs when a Postgres URL is present (Part 1.5).

## 5. What M1 does NOT do
No ingestion (M2), no API/dashboard/WhatsApp (M3), no models (M4), no web review UI (M3),
no context_signal or ingest_run tables (they arrive with the connector in M2), nothing
YouTube-shaped (Gate 1).

## 6. Open questions — genuine forks I need answered before/at build

### 6.1 Where does the Agmarknet registry seed come from? — **needs your call**
The spec says "seed from official Agmarknet commodity and variety lists." Those lists live
behind data.gov.in (API key) or the Agmarknet portal. Options:
- **(A) Give me the `data.gov.in` API key now** → I pull the real commodity/variety/market
  master once, save it as the checked-in seed, and M1 seeds from the genuine list.
- **(B) Recommended: bootstrap now, full import at M2.** I build a **small, hand-verified
  seed of the top ~25–30 Delhi F&V commodities/varieties/markets** from the *public*
  Agmarknet commodity list (citable, not invented), ship M1 on that, and import the full
  master when the key arrives with the M2 connector. This keeps M1 unblocked.
I recommend **(B)** unless the key is handy, in which case **(A)** is strictly better.

### 6.2 Where do the 200 labelled aliases come from? — **needs your call**
Part 3.2 says "200 aliases extracted from the real corpus … which I will verify." **The
real corpus does not exist yet** (video is Gate-1 blocked; Agmarknet isn't ingested). So
for M1 I propose a **bootstrap labelled set of 200 real aliases** drawn from genuine,
verifiable produce naming — English (Agmarknet), Devanagari + Hinglish (well-established
names like आलू/aloo→potato, प्याज़/pyaaz→onion, शिमला मिर्च/shimla mirch→capsicum), and a
handful of **real** retail SKU titles you provide — **for you to verify.** It is a
stand-in: accuracy on it is *indicative*, and it gets replaced/augmented once the real
corpus exists (M2/M6). **OK to proceed this way, and can you supply ~20–30 real
quick-commerce SKU titles** for common vegetables to make the set realistic? (No scraping —
manual paste is fine.)

### 6.3 Second matcher: phonetic vs embeddings? — **my recommendation, confirm**
I propose evaluating **A: lexical+transliteration** vs **B: phonetic** (both light). I'm
**deferring the embedding/torch approach** to respect the ₹25k box. If you specifically
want embeddings benchmarked now, say so and I'll add it (and note the box needs more RAM).

### 6.4 New deps OK? §2 lists five light libraries (no torch). Confirm.

### 6.5 Review interface: CLI now, web UI at M3 — confirm that split.

### 6.6 Is building `price_observation`'s schema in M1 (rows in M2) the right split? I
believe yes — the guard test needs the table. Flagging in case you'd rather M1 be
registry-only.

## 7. Recommended split (Part 1.2)
M1 is two sittings. I recommend:
- **M1a — Data model core:** all tables, migrations, repository + **source-class guard**,
  provenance/append-only, unit-convention, registry seed. **DoD:** guard test passes;
  registry seeded. *(Delivers DoD #1.)*
- **M1b — Entity resolution:** matchers A & B, the 200-alias eval harness, review-queue
  CLI, `R9` tag. **DoD:** 200-alias set runs with reported accuracy. *(Delivers DoD #2.)*
Each is independently reviewable and each ends green with real output. If you'd rather keep
M1 whole, I'll build it in that internal order anyway.

## 8. Estimated size
Medium–large (hence the proposed split). No single piece is research-risky; the matcher
accuracy *number* is the one genuinely empirical unknown, and I'll report it straight —
including if the lexical/phonetic approaches turn out mediocre on Indian transliteration.

## 9. Cost impact
₹0 fixed (all new deps are libraries; no new infra). `RUNNING_COSTS.md` unchanged except a
note that the embedding path stays deferred.
