# BUILD_PROMPT — Source of Record

> **Provenance note.** This file is the authoritative specification for the build.
> It is a faithful capture of the build prompt pasted by the founder on
> **2026-09-10**. The prompt was written to sit alongside two external documents —
> `docs/blueprint.md` (product blueprint) and `docs/research-brief.md` (a validation
> study dated 2026-09-09). **Neither external file was available** when work began;
> a search of the working directory and the founder's Downloads produced adjacent
> Vervana material (a warehouse-orchestration investor blueprint, a mandi
> warehousing PPP concept note, handwritten price-analysis notes) but *not* the two
> documents this prompt was written against. Per the founder's explicit decision on
> 2026-09-10, this prompt is treated as the **self-contained combined spec**. It
> already inlines the substance of both missing files: Parts 3–6 carry the
> blueprint's core (data model, connectors, analytics, milestones), and Part 2 plus
> the Gate-2 figures carry the research brief's core (the R1–R12 evidence with
> citations, the TAM/SAM numbers, the study designs, the forecasting constraints).
> The one sub-task that strictly required both files as separate artifacts —
> "flag every place the blueprint and the research brief conflict" — is reinterpreted
> as "flag internal tensions in this combined spec." See `UNDERSTANDING.md`.

---

## Role

Lead engineer building Vervana's price-intelligence and procurement platform for
Indian fresh produce, starting with Delhi mandis. Greenfield build. Where the
(now-absent) research brief would have conflicted with the blueprint, the research
brief wins; conflicts are to be surfaced each time noticed. Build Phases 0–3. Large,
multi-session build; work methodically, do not produce everything at once.

## PART 0 — TWO HARD GATES BEFORE ANY CODE (blocking; no workarounds)

**Gate 1 — Legal opinion on data collection.** YouTube ToS prohibits automated
access/scraping and non-personal/commercial reuse of Content
(https://www.youtube.com/static?template=terms). The founder is obtaining written
counsel on whether extracting factual price statements from transcripts for internal
analysis is defensible under s.52 fair dealing of the Indian Copyright Act. Until the
founder confirms the opinion has arrived and states what it says: **write no code
that fetches from YouTube, and no parser that assumes a YouTube-shaped input.** Build
the Agmarknet path first. Design transcript ingestion as a pluggable connector behind
an interface so it can be added — or permanently dropped — without touching anything
else.

**Gate 2 — Stack ADR, approved by the founder.** Write `docs/adr/0001-stack.md`
choosing the stack. Evaluate ≥3 viable options against:
- Founding team non-technical; maintainability by a junior Indian developer matters
  more than elegance.
- **Market is small.** TAM ≈ ₹154 crore/yr at 100% penetration; Delhi-NCR SAM ≈
  ₹6.6 crore/yr; realistic year-one ceiling ₹20–29 lakh ARR. A stack whose fixed
  monthly cost exceeds **₹25,000** is disqualified on arithmetic alone.
- Direct competitor MandiBhav sells alerts from ₹99/mo (https://mandibhav.in/);
  Agmarknet gives the underlying data away free. No room for expensive architecture.
- Core workload is daily-batch time-series ingest, entity resolution, small-scale
  model training — not high-concurrency serving.
- Text must handle Devanagari and Hinglish transliteration.
- Deployment in India; data residency preferred.

State the choice, alternatives rejected, the specific reason for each rejection, and
a monthly running-cost estimate at 10, 100, 1,000 users. Then stop and show the ADR.

## PART 1 — HOW TO WORK

1. **Milestones, not one pass.** Per milestone: write `docs/milestones/MXX-plan.md`
   (files, tests, open questions) → show and wait → build → run tests, show **real
   output** → write `docs/milestones/MXX-done.md` → commit → next. No skipping or
   pre-scaffolding later milestones.
2. **Working code beats broad scaffolding.** 3 milestones that work > 8 of `# TODO`.
   If a milestone is bigger than it looked, say so and propose a split.
3. **Every claim backed by something runnable.** Row counts + sample rows for
   ingests; real parsed output incl. failures for parsers; backtest tables with
   baselines for models. **Fabricated/assumed results are the worst failure mode.**
4. **Ask about genuine forks, decide the rest.** Business rules not specified, data
   formats that can't be inferred, legal questions → ask with options + a
   recommendation. Naming/layout → just decide.
5. **No network calls in tests.** Recorded fixtures; tests pass offline. Live-
   integration tests are a separate, opt-in suite.
6. **Cost is a feature.** Log estimated monthly running cost of every component to
   `docs/RUNNING_COSTS.md`. If cumulative fixed cost passes ₹25,000/mo, stop and tell
   the founder.

## PART 2 — RISK ANNOTATION SYSTEM

Build the blueprint as written, but flag every load-bearing assumption **in the code
at the exact point it is load-bearing**, using:

```
# RISK[<ID>]: <assumption> — why it may be wrong — what breaks if it is.
# Evidence: <reference>
# Verdict: PENDING
```

Maintain `docs/RISK_REGISTER.md` as a live index **generated by a script that greps
for `RISK[`**. Run it at the end of every milestone. The register must never drift
from the code.

Risks to tag (evidence in full form retained in `docs/RISK_REGISTER.md` seed):

| ID | Assumption | Evidence against |
|---|---|---|
| `R1-INFO-CHANGES-BEHAVIOUR` | Better price data changes decisions | Mitra, Mookherjee, Torero & Visaria (2017): 72-village RCT, daily potato mandi prices for 11 months → **no significant impact** on farm-gate prices/quantities. |
| `R2-BEACHHEAD` | Delhi mandi traders are first customers | They *generate* the price at 5 AM (Azadpur: 2,224 licensed traders). Study ranks them **last** on WTP; HoReCa chains first. |
| `R3-VIDEO-PROVENANCE` | Video quotes ≈ near-executed "aadat" prices | Never measured. |
| `R4-WEAK-GROUND-TRUTH` | Agmarknet validates video quotes | DMI disclaims its own data; Aug 2025 Assam board pulled up for zero submissions Jun–Jul 2025. **Ground truth = trader invoices.** Agmarknet is a third comparator. |
| `R5-COVERAGE-EDGE` | Agmarknet Delhi coverage bad enough to beat | **Unmeasured; entire edge rests on it.** Documented failure is Assam, not Delhi. If Delhi coverage >90% of commodity-days same-day, coverage advantage doesn't exist. |
| `R6-MOAT-MODEL-GAP` | Video corpus is defensibility AND model trains on Agmarknet history | Both can't be load-bearing. Log video-feature importance each run; <5% aggregate ⇒ corpus doesn't defend the forecast. |
| `R7-FORECAST-BAR` | Gradient boosting beats naive baselines on next-day F&V | Daily F&V ≈ random walk + weather shocks; ~90 obs/series too few for trees, none for DL. Baselines always computed and reported. |
| `R8-YOUTUBE-TOS` | Corpus is both legal risk AND defensible asset | Can't be both. An asset that can't enter a data room is a research seed, not a moat. |
| `R9-NOT-IP` | Dataset is proprietary IP | *EBC v. D.B. Modak* (SC 2008): "modicum of creativity"; bare factual compilations unprotected. Prices are facts. Only entity-resolution editorial judgment may attract protection. |
| `R10-QCOMM-SOURCING` | Buying q-comm feeds from vendors is compliant | Moves the ToS breach one party away, doesn't remove it. |
| `R11-RECORDER-CONFLICT` | Commission agents can be paid to report reliably | They hold positions in what they report. Structural conflict. Schema records observer identity + whether they trade in what they report. |
| `R12-RECORDER-ECONOMICS` | Platform scales like software | Observer payroll scales linearly with mandi count against a ₹6.6 cr NCR SAM. Emit monthly observer-cost estimate wherever a mandi is added. |

Add new tags when another faith-based assumption is found, and tell the founder.

## PART 3 — DATA MODEL

**3.1 `price_observation` (single fact table).**
- `source_class` enum, exactly four, never coerced: `quote_indicative`,
  `executed_summary`, `executed_trade`, `retail_offer`. Repository-layer guard blocks
  averaging across classes; test proves a naive "average potato price today" is
  blocked.
- Ranges never collapsed at write time: `price_low`/`price_high` primary; `price_point`
  nullable, set only when the source gives one number.
- `unit_raw` immutable; canonical ₹/kg in derived columns storing the conversion
  factor used + `unit_conversion_confidence`.
- Provenance is a DB constraint: every row carries `source_url` and `raw_quote` (or
  raw payload); untraceable rows fail insertion.
- `time_basis` enum: `exact`, `estimated_window`, `single_daily_quote`,
  `daily_summary`. Estimated timestamps never indistinguishable from real ones.
- Append-only; corrections create a new row with `supersedes_id` + reason. Never
  UPDATE a price in place.

**3.2 Entity registry** (most valuable component; only colourable-IP component per R9).
Tables `commodity`, `variety`, `grade`, `market`, plus `alias(alias_text,
alias_language, alias_source_type, canonical_type, canonical_id, confidence,
created_by, verified_by, verified_at, notes)`. `alias_source_type` ∈
{`agmarknet_official`, `hindi_spoken`, `hinglish_transliteration`, `qcomm_sku_title`,
`trader_colloquial`}. Seed from official Agmarknet lists, then extend. Automated
matches marked unverified → human review queue; promotion requires a recorded
reviewer. Transliteration-aware fuzzy matching ("shimla mirch", "शिमला मिर्च",
"Shimla Mirchi", "capsicum" all resolve). Evaluate two approaches; report accuracy vs
a hand-labelled 200-alias set from the real corpus (founder verifies). Many-to-many is
the reality.

**3.3 Bag-weight lookup.** `unit_convention(market_id, commodity_id, unit_raw,
kg_equivalent, source, confidence, effective_from, effective_to)`. Never hardcode
50 kg. Unknown weight ⇒ store raw unit, canonical price NULL. Don't guess.

## PART 4 — DATA SOURCES (each an independent connector behind a common interface,
disableable via config; each: fetch → normalise → validate → emit rows → record
ingest-run metadata)

- **4.1 Agmarknet via data.gov.in — first.** Resource
  `9ef84268-d588-465a-a308-a864a43d0070`. Pagination (1,000 cap), API key from env
  (never committed), exponential backoff, snapshot-needs-daily-capture, missing/zero
  prices, spelling variance in market names. Separate historical backfill from daily
  incremental. Store raw payload before parsing. Licence: GODL-India (commercial reuse
  with attribution) — exact clause text unread (robots-blocked); surface licence
  attribution + DMI disclaimer in product; flag in `docs/OPEN_QUESTIONS.md`.
- **4.2 YouTube transcript ingest — blocked by Gate 1.** When/if unblocked: aggressive
  local cache (never fetch a video twice), conservative configurable rate limiting,
  429 pause-not-retry, hard kill switch. Parser extracts date, commodity,
  variety/origin, quoted range, unit, arrivals, carryover, commentary, raw quote,
  extraction confidence. Digit-merge detection (e.g. `4546` → `45–46`), range sanity
  bounds learned from Agmarknet history. **Flag, never silently correct.**
- **4.3 Field-observer ingest** — voice notes → ASR → same parser. Observer identity
  records whether they trade in the commodities they report (R11); every observation
  carries independence status. Per-observer accuracy scorecard.
- **4.4 eNAM** — executed e-auction prices, highest-quality public source where
  coverage exists. **No documented open API found**; live dashboard exists. Build the
  connector interface; record unresolved access method in `docs/OPEN_QUESTIONS.md`.
- **4.5 Quick-commerce** — connector interface + manual-panel CSV import path. **No
  scraper.** Vendor-feed path is a documented stub carrying R10. Normalise pack prices
  to ₹/kg while retaining pack size, MRP, selling price, fees separately.
- **4.6 Context signals** — weather, diesel, festival calendar → `context_signal`
  table (features, not price observations).

## PART 5 — ANALYTICS & MODELLING

- **5.1 Agmarknet Delhi coverage study (R5).** Azadpur + Keshopur, 90 days: % of
  commodity-days with a reported price, reporting-lag distribution, count of
  implausible values, per-commodity breakdown. Standalone reproducible report.
  Measures whether the product has an edge at all.
- **5.2 Ground-truth study (R3, R4).** Reference = **trader invoices**, not Agmarknet.
  Median absolute % deviation between video-quote midpoint and invoiced price, per
  commodity. Agmarknet is a third comparator only. Pluggable additional ground-truth.
- **5.3 Forecasting.** Strict order; never ship a model not compared to all three
  baselines: naive (tomorrow=today), seasonal-naive (same weekday last week), 7-day
  MA. Then SARIMA/Prophet. Then gradient boosting. Constraints: ~90 obs/series ⇒ enough
  for baselines and marginal weekly-seasonal SARIMA, **not** per-series trees, **not**
  LSTM (do not build). Pooling across commodities means training mostly on Agmarknet
  multi-year history (the R6 problem); log/report video-feature importance every run.
  Annual seasonality unlearnable from 90 days; don't claim it. **Evaluation harness
  matters more than models:** expanding-window walk-forward (never random split);
  report MAE (₹/kg), sMAPE, directional accuracy, PI coverage — per commodity, beside
  baselines; plus decision-level simulated P&L of a buy/hold/sell rule vs the same rule
  on naive. **Kill criterion enforced in code:** if GB doesn't beat seasonal-naive by
  >10% directional accuracy, serving exposes baseline+interval only, labelled as such
  in API and UI, via a runtime check against stored backtest results. Build the public
  prospective forecast log from day one (tomorrow's call posted today, scored daily,
  published unedited).
- **5.4 Confidence scoring.** `price_confidence` = source reliability × extraction
  confidence × cross-source agreement; each factor independently inspectable;
  composite explainable in plain words per row.

## PART 6 — MILESTONES (reordered from v1: serving ahead of forecasting; transcript
ingest at M6 — both deliberately, since the forecast may not clear its bar and the
transcript pipeline may be legally unusable)

- **M0 Foundations.** Stack ADR approved. Repo skeleton, deps, lint, format,
  pre-commit, test harness, structured logging, config w/ secrets from env, Docker
  Compose local dev, CI. *Done:* `make test` green from clean clone in one command; CI
  green.
- **M1 Data model + entity registry.** Schema, migrations, repository layer w/
  source-class guard, registry seeded from Agmarknet lists, alias table, fuzzy matcher,
  unit-convention table, review-queue backend. *Done:* 200-alias labelled set runs with
  reported accuracy; source-class guard test passes.
- **M2 Agmarknet ingest + coverage study.** Daily incremental, historical backfill,
  ingest-run tracking, retry/rate-limit handling, then §5.1. *Done:* real rows in DB
  (counts + samples shown); deliberate API failure handled without data loss; Delhi
  coverage report exists with R5 verdict recorded.
- **M3 Serving layer v1.** API, minimal dashboard, WhatsApp digest. Every displayed
  price links to its evidence, shows source class + confidence. *Done:* any number is
  click-through to its API row. Ship early.
- **M4 Forecasting harness.** Baselines, walk-forward backtest, decision-level P&L,
  prospective log, then SARIMA/Prophet, then GB with kill-criterion enforcement.
  *Done:* comparison table with baselines; runtime kill-check demonstrated firing both
  directions.
- **M5 Ground-truth study.** Per §5.2, vs invoices. *Done:* reproducible from one
  command; every dependent RISK verdict moved from PENDING to a stated verdict with
  evidence.
- **M6 Transcript ingest.** Gated on Gate 1. Cache, rate limiter, kill switch, parser,
  digit-merge, flagging, review queue. *Done:* corpus parsed with reported flag rate;
  show 20 parsed rows incl. 3 failures with explanations.
- **M7 Additional connectors.** eNAM, field observers (independence tracking),
  q-comm manual panel, context signals. *Done:* each independently disableable via
  config without breaking anything, proven by test.
- **M8 Phase 2/3 expansion.** Multi-mandi config emitting R12 cost estimate, intraday
  modelling where data supports, authenticated rate-limited public API, B2B
  benchmarking views, historical export. *Done:* adding a mandi is a config change, not
  code; demonstrated.

## PART 7 — NON-NEGOTIABLE CONSTRAINTS

- Nothing scrapes a site whose terms prohibit it; if about to write a q-comm scraper,
  stop and tell the founder.
- Every user-facing number carries provenance, source class, confidence — incl. the
  WhatsApp digest.
- DMI accuracy disclaimer wherever Agmarknet is displayed; GODL-India attribution in
  footer.
- Forecasts always an interval + confidence, never a bare point; always a
  not-trading-advice disclaimer.
- Asia/Kolkata everywhere. Store UTC, display IST, no naive datetimes in the DB.
- Money as integer paise. Never floats.
- No secrets in the repo; provide `.env.example`.
- Observer/trader PII minimised and access-controlled.
- No APMC licence needed to publish price info; one is needed to trade notified
  commodities. If any feature moves toward taking a procurement position, stop and flag
  it (regulatory line + Essential Commodities Act stock-limit exposure).

## PART 8 — DOCUMENTATION TO MAINTAIN

`README.md`; `docs/adr/`; `docs/RISK_REGISTER.md` (generated, never hand-edited);
`docs/RUNNING_COSTS.md`; `docs/OPEN_QUESTIONS.md` (eNAM API access, GODL clause text,
GST treatment of a data subscription); `docs/DATA_DICTIONARY.md` (every table/column:
meaning, source, what it must never be used for); `docs/RUNBOOK.md` (ingest fails, key
expires, parser flags everything); `docs/milestones/` (plan + done).

## PART 9 — START HERE (do in order, then stop and report)

1. Read both source docs completely; write `docs/UNDERSTANDING.md` — independent
   restatement, hard parts, every blueprint/research conflict, any internal
   inconsistency.
2. Write `docs/adr/0001-stack.md` per Gate 2, incl. cost estimates.
3. Write `docs/milestones/M0-plan.md`.

Then stop. No application code until the ADR is approved and Gate 1 is cleared.

**Standing instruction:** if the code starts showing the research brief's pessimistic
thesis is right — coverage study shows no edge, ground truth fails, forecast can't beat
naive — **say so plainly rather than building around it.**
