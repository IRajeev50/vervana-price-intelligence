# UNDERSTANDING — Independent restatement

**Author:** lead engineer (Claude) · **Date:** 2026-09-10 · **Status:** pre-code, pre-ADR-approval

> **On sources.** The prompt was written against two files — a product `blueprint.md`
> and a `research-brief.md` (validation study, 2026-09-09). Neither was available;
> the founder directed me to treat the pasted prompt as the self-contained combined
> spec (see [`BUILD_PROMPT.md`](BUILD_PROMPT.md)). Consequence for PART 9: I cannot
> enumerate *blueprint-vs-research conflicts* as two separable documents, because the
> two voices are already merged into one text. What I *can* do — and do below — is
> flag the **internal tensions and one ordering inconsistency** that survive inside
> the merged spec. Several of these are exactly the places the research voice would
> have contradicted the blueprint voice; I mark those as **[merged conflict]**.

---

## 1. What is actually being built (my words, not the prompt's)

A **provenance-first price-observation database** for Indian fresh produce, Delhi
first, plus the thin analytics and delivery layers that sit on top of it. Strip away
the ambition and the system is three honest things:

1. **A fact store that refuses to lie by aggregation.** Every price is stored with
   where it came from, what *kind* of price it is (an indicative quote vs a real
   executed trade vs a retail shelf price), whether its timestamp is real or guessed,
   and in what unit — and the schema physically prevents someone from averaging a
   Blinkit potato price with an Azadpur wholesale quote and calling it "today's potato
   price." The audit trail *is* the product.

2. **An entity registry that resolves the mess of Indian produce naming** — "shimla
   mirch" / "शिमला मिर्च" / "Shimla Mirchi" / "capsicum" all pointing at one commodity,
   across official lists, spoken Hindi, Hinglish, retail SKU titles and trader slang,
   many-to-many, with a human-in-the-loop verification queue. Per R9 this is the
   *only* component with a defensible IP claim, because it is the only one containing
   editorial judgment rather than bare fact.

3. **Delivery + decision layers** — an API, a minimal dashboard, a WhatsApp digest
   (M3), and a forecasting harness whose real deliverable is the *evaluation harness
   and the public prospective log*, not the models (M4).

Everything else — the connectors (Agmarknet, and later YouTube/eNAM/observers/
quick-commerce/context), the coverage study, the ground-truth study — is either
plumbing that feeds the fact store or an **experiment designed to tell the founder
whether the business thesis is true.**

That last framing is the key to this project. **This is not a normal build; it is a
build-to-decide.** The spec is engineered to falsify its own product thesis as cheaply
as possible. My job is as much to run three experiments honestly (M2 coverage, M5
ground truth, M4 forecast-vs-naive) as it is to ship features — and to say plainly if
they come back negative.

## 2. The hard parts (ranked by how much they can hurt us)

1. **Getting trader invoices at all (M5).** The whole ground-truth study rests on
   invoices being the reference — but invoices are not a public dataset, they come
   from *relationships with traders/HoReCa buyers.* This is a non-code dependency the
   spec assumes away. If the founder cannot supply a real invoice sample, M5 cannot
   resolve R3/R4/R6, and those verdicts stay PENDING forever. **This is the single
   biggest external risk and I will need a source of invoices before M5.**

2. **Measuring Delhi coverage honestly (M2/§5.1).** The entire edge is the hypothesis
   that Agmarknet's Delhi coverage is bad. It is *unmeasured*. The documented failure
   is Assam, not Delhi (R5). Getting this measurement right — not p-hacking it to
   flatter the product — decides whether the product has a reason to exist. It must be
   a standalone reproducible report, and I must report a >90% same-day result as
   *"the coverage edge does not exist"* even though that undercuts the build.

3. **Entity resolution quality against a real, messy corpus.** Transliteration-aware
   fuzzy matching evaluated against a hand-labelled 200-alias set. This is the actual
   ML of the project and the actual asset. Getting to a trustworthy accuracy number
   (and an honest human-review queue) is genuinely hard and genuinely valuable.

4. **Not fabricating results while swimming in noisy, missing data.** Agmarknet has
   zeros, missing days, and market-name spelling drift; video quotes are indicative;
   observers are conflicted. The temptation to silently impute/collapse/average is
   everywhere, and every such shortcut is a lie to the founder and eventually the
   user. The schema constraints (source_class guard, ranges-not-collapsed,
   provenance-required, append-only) exist precisely to make lying hard. I must not
   engineer around them.

5. **Keeping the RISK register generated-from-code and never drifting.** Easy to state,
   easy to let rot. The grep-generated register is a discipline mechanism; if it drifts
   the whole risk-annotation system is theatre.

6. **Cost discipline under a ₹25,000/mo software ceiling with India residency.** Tight
   but achievable for a daily-batch workload. The trap is compute spikes (ASR for
   observers, transcript processing) and managed-service creep. See the ADR.

## 3. Internal tensions and inconsistencies I am flagging now

### 3.1 The moat is attacked three times by the spec's own risk register — **[merged conflict]**
R6 (video corpus can't be both the moat *and* something the model can't lean on),
R8 (it can't be both a legal risk *and* a data-room asset), and R9 (facts aren't IP;
only entity-resolution editorial judgment is) together **dismantle the "defensible
proprietary dataset" thesis.** My read: the durable asset is the **entity registry**,
not the price corpus. I will treat registry quality as the top engineering priority
because it is the one thing that survives every way the thesis can break — including a
full pivot to procurement infrastructure. This is not a contradiction to resolve in
code; it is a strategic finding the build should keep confirming or refuting.

### 3.2 Who is the paying customer? — **[merged conflict] · needs a founder decision**
The blueprint voice targets **Delhi mandi traders**; the research voice (R2) ranks
them *last* on willingness to pay and puts **HoReCa chains first**. Yet M3 ships a
**WhatsApp digest**, which is shaped like a trader/farmer product, not a HoReCa
procurement product. The spec never resolves the persona. This matters for M3's design
(what the digest contains, what the dashboard shows, what "evidence link" a HoReCa
buyer needs vs what a trader needs). **I will need a decision before M3, and I'll ask
then with options.** Provisionally I'll build M3's core (provenance-linked price views)
persona-neutral so it serves either.

### 3.3 R1's evidence may not transfer to the real buyer — **independent doubt about the spec**
R1 cites the Mitra-Mookherjee-Torero-Visaria RCT: giving *farmers* daily prices didn't
change *farm-gate outcomes*. But the product's stated buyer (per R2) is a **procurement
buyer** (HoReCa), whose decision context — when/where/how much to buy — is different
from a smallholder's selling decision and plausibly more information-elastic. So R1 is
strong evidence against a *farmer-facing* product and **weaker, possibly misapplied,
evidence against a buyer-facing one.** I'll still tag R1 where the code assumes
info→action, but I'm recording my view that R1 should ultimately be tested on the
*actual* buyer, not treated as settled. This is a place I think the spec slightly
over-generalises its own evidence.

### 3.4 Milestone ordering: M5 (ground-truth on video quotes) precedes M6 (video ingest) — **inconsistency**
M5's ground-truth study compares **video-quote midpoints** to invoices and is expected
to move R3 from PENDING to a verdict. But the pipeline that *produces* parsed video
quotes is **M6**, which is ordered *after* M5 and is *gated on Gate 1* (and may never
be built). You cannot study the accuracy of video quotes before you can extract them,
and you cannot commit to studying them if the legal gate forbids extracting them.
**Resolution I propose:** M5 ships in two layers — (a) an **Agmarknet-vs-invoice**
comparison that needs no video and resolves R4/R5-adjacent questions immediately; and
(b) a **video-vs-invoice** layer that consumes a *small hand-extracted video-quote
sample* (not the M6 pipeline) so R3 can get a provisional verdict even if M6 never
ships. If Gate 1 comes back negative, R3/R6/R8 resolve to *"corpus unusable — thesis
fails on legal grounds"* and M5(b) is moot. I'll build M5 this way unless told
otherwise.

### 3.5 Ranges are never collapsed — but forecasting and deviation need a single number — **latent assumption, candidate new RISK**
The data model deliberately refuses to pick a point price at write time (price_low/
price_high primary). But §5.2 computes deviation on the **range midpoint**, and
forecasting needs a scalar series per commodity. So a *point projection* (midpoint, or
something else) is unavoidable at the modelling layer — and "midpoint = the price" is an
untested assumption (skew, thin tails, quote-vs-trade spread all violate it). **I
propose a new tag `R13-RANGE-MIDPOINT`**: treating the midpoint of a quoted range as
the representative price for modelling and deviation. I'll add it when the modelling/
deviation code is written (M4/M5) and flag it here per the "tell me when you add a tag"
instruction.

### 3.6 Confidence scoring vs the source-class guard — **design care needed**
§5.4's "cross-source agreement" factor compares across sources, but §3.1's guard
forbids comparing across source_class (retail vs wholesale). Agreement is not the same
as averaging, so this isn't a contradiction — but the confidence calc must compute
agreement **within comparable source classes** (or model the wholesale→retail spread
explicitly), or it will smuggle the exact category error the guard exists to prevent.
Noted so I don't build it wrong.

### 3.7 Append-only + `supersedes_id` vs "average price today" — **design care needed**
The guard blocks cross-class aggregation, but append-only means superseded rows still
sit in the table. Any aggregate (even a legitimate within-class one) must exclude
`supersedes_id`-chained-away rows or it double-counts. The guard/repository layer has to
enforce "latest, non-superseded, single class" — not just "single class." Minor but easy
to get wrong.

### 3.8 The best public source is the least accessible — **acknowledged, not resolvable now**
eNAM carries *executed* auction prices (the highest-quality public source per §4.4) but
has **no documented open API** — only a dashboard. So our highest-quality public data is
behind the connector we can't finish. Interface + stub + OPEN_QUESTIONS entry is the
only honest move. Noted.

### 3.9 The ₹25,000/mo ceiling governs software, not the real cost — **scope reminder**
The fixed-cost ceiling disciplines the *software* stack. But R12 says the real cost
driver is **observer payroll**, which scales linearly with mandi count against a
₹6.6 cr NCR SAM and is opex, not the ₹25k software line. The ceiling is necessary but
not the binding constraint on the business; I'll keep the two cost stories strictly
separate in `RUNNING_COSTS.md`.

## 4. What I believe, said plainly (the standing instruction)

On the spec's *own* evidence, the most probable outcome is:
- **M2 coverage study:** Delhi coverage is better than the thesis needs it to be, so the
  "we have data Agmarknet doesn't" edge is thin; what remains is **intraday timing**,
  which is a much narrower claim.
- **M5 ground truth:** video quotes deviate enough from invoices that they are a
  **sentiment/leading signal, not a price**, collapsing the intraday-price thesis too.
- **M4 forecast:** gradient boosting **does not beat seasonal-naive** by the 10% bar, so
  serving ships baselines+intervals and the "AI forecast" is a label, not a moat.

If that is how it lands, the honest conclusion — which the founder has already
anticipated — is that **the price-data product is a weak standalone business, and the
real value is (a) the entity-resolution registry and (b) procurement infrastructure
that uses this dataset as an internal instrument, not a sold product.** I am building
the platform as instructed, with eyes open, and I will report each experiment's result
straight, including when it argues for the pivot.

The lowest-regret engineering priority across *every* way this resolves is the **entity
registry** (M1): it is the defensible asset, it is needed by the procurement pivot, and
it is the input quality gate for every downstream number. I'll invest there first and
hardest.

## 5. Immediate non-code blockers I need from the founder (not now — flagged for the right milestone)

- **Gate 1 legal opinion** (blocks M6 and the video-dependent risk verdicts).
- **Gate 2 ADR approval** (blocks all code) — see [`adr/0001-stack.md`](adr/0001-stack.md).
- **Customer/persona decision** (blocks M3 design) — §3.2 above.
- **A real trader-invoice sample** (blocks M5) — §2.1 above.
- **data.gov.in API key** (needed at M2; must arrive via env, never committed).
