# RISK REGISTER

> **Generated file — do not hand-edit.** Produced by `scripts/gen_risk_register.py` (run via `make risks`) from `scripts/risks_seed.yaml` (definitions) and a grep of the codebase for `RISK[<ID>]:` tags (live occurrences). Edit the seed or the code, then regenerate.

**Summary:** 13 risks declared · 13 have live code tags · 0 not yet reached in code · 14 tag occurrences total.

## 1. Declared risks (definitions)

| ID | Assumption | Code tags | Verdict(s) |
|---|---|---|---|
| `R1-INFO-CHANGES-BEHAVIOUR` | Giving people better price data changes their decisions. | 1 | PENDING |
| `R2-BEACHHEAD` | Delhi mandi traders are the first customers. | 1 | RESOLVED — persona set to HoReCa + quick-commerce (2026-09-10, founder). |
| `R3-VIDEO-PROVENANCE` | Video-quoted ranges are near-executed "aadat" prices comparable to trades. | 1 | PENDING |
| `R4-WEAK-GROUND-TRUTH` | Agmarknet validates video quotes. | 2 | PENDING; PENDING — no trader invoices supplied yet. |
| `R5-COVERAGE-EDGE` | Agmarknet's Delhi coverage is bad enough that we beat it. | 1 | PENDING — PRELIMINARY LIVE 2026-09-10 09:30 IST: the national daily snapshot |
| `R6-MOAT-MODEL-GAP` | The video corpus is the defensibility AND the model trains on Agmarknet history. | 1 | PENDING — video-feature contribution = 0% (no video features exist yet) |
| `R7-FORECAST-BAR` | Gradient boosting beats naive baselines on next-day F&V prices. | 1 | PENDING (no real multi-day history captured yet; see M4-done) |
| `R8-YOUTUBE-TOS` | The corpus is both a legal risk and a defensible asset. | 1 | PENDING — legal opinion not yet confirmed; treated as manual import only. |
| `R9-NOT-IP` | The dataset is proprietary IP. | 1 | PENDING |
| `R10-QCOMM-SOURCING` | Buying quick-commerce feeds from data vendors is compliant. | 1 | PENDING |
| `R11-RECORDER-CONFLICT` | Commission agents can be paid to report prices reliably. | 1 | PENDING |
| `R12-RECORDER-ECONOMICS` | The platform scales like software. | 1 | PENDING |
| `R13-RANGE-MIDPOINT` | The midpoint of a quoted range is the representative price for modelling and deviation. | 1 | PENDING |

## 2. Live code tags (grepped from source)

| ID | Location | Summary | Verdict |
|---|---|---|---|
| `R1-INFO-CHANGES-BEHAVIOUR` | `src/vervana/digest.py:155` | This digest assumes that showing a buyer the | PENDING |
| `R10-QCOMM-SOURCING` | `src/vervana/connectors/quickcommerce.py:51` | A "vendor feed" of quick-commerce prices is not a | PENDING |
| `R11-RECORDER-CONFLICT` | `src/vervana/models/observer.py:23` | A paid recorder who holds positions in the commodities | PENDING |
| `R12-RECORDER-ECONOMICS` | `src/vervana/economics.py:44` | The platform is assumed to scale like software, but | PENDING |
| `R13-RANGE-MIDPOINT` | `src/vervana/forecast/series.py:26` | The modelled series uses `canonical_price_paise_per_kg`, | PENDING |
| `R2-BEACHHEAD` | `src/vervana/digest.py:28` | This digest is deliberately shaped for HoReCa buyers, not mandi | RESOLVED — persona set to HoReCa + quick-commerce (2026-09-10, founder). |
| `R3-VIDEO-PROVENANCE` | `src/vervana/connectors/transcript.py:98` | These are YouTube-quoted ranges treated as prices. | PENDING |
| `R4-WEAK-GROUND-TRUTH` | `src/vervana/analytics/groundtruth.py:181` | The reference MUST be trader invoices, never Agmarknet — | PENDING — no trader invoices supplied yet. |
| `R4-WEAK-GROUND-TRUTH` | `src/vervana/connectors/agmarknet.py:235` | We record Agmarknet as `executed_summary` — a | PENDING |
| `R5-COVERAGE-EDGE` | `src/vervana/analytics/coverage.py:69` | The entire product edge assumes Agmarknet's Delhi coverage | PENDING — PRELIMINARY LIVE 2026-09-10 09:30 IST: the national daily snapshot |
| `R6-MOAT-MODEL-GAP` | `src/vervana/forecast/models.py:64` | The corpus is pitched as the moat, yet the model trains on | PENDING — video-feature contribution = 0% (no video features exist yet) |
| `R7-FORECAST-BAR` | `src/vervana/forecast/models.py:56` | This assumes gradient boosting can beat the naive baselines on | PENDING (no real multi-day history captured yet; see M4-done) |
| `R8-YOUTUBE-TOS` | `src/vervana/connectors/transcript.py:58` | This corpus is YouTube-derived. It cannot be both a legal | PENDING — legal opinion not yet confirmed; treated as manual import only. |
| `R9-NOT-IP` | `src/vervana/models/entities.py:26` | This registry is treated as proprietary IP. Under Eastern Book | PENDING |

## 3. Evidence against each assumption

### `R1-INFO-CHANGES-BEHAVIOUR`

- **Assumption:** Giving people better price data changes their decisions.
- **Evidence against it:** Mitra, Mookherjee, Torero & Visaria (2017): a 72-village West Bengal RCT delivered daily wholesale mandi prices to potato farmers for 11 months and found no significant impact on average farm-gate prices or quantities sold (high- and low-price effects cancelled). https://people.bu.edu/dilipm/publications/MMTV_18537_Paper.pdf
- **Note:** Independent doubt (UNDERSTANDING.md 3.3): this is farmer-side evidence; the product's stated buyer (R2) is a HoReCa procurement buyer whose decision context differs and may be more information-elastic. Test on the real buyer.

### `R2-BEACHHEAD`

- **Assumption:** Delhi mandi traders are the first customers.
- **Evidence against it:** Traders generate the price at 5 AM (Azadpur alone: 2,224 licensed traders, https://www.apmcazadpurdelhi.com/home/about). The study ranks them LAST on willingness to pay and HoReCa chains FIRST.

### `R3-VIDEO-PROVENANCE`

- **Assumption:** Video-quoted ranges are near-executed "aadat" prices comparable to trades.
- **Evidence against it:** Never measured. The ground-truth study (M5) compares video quotes to trader invoices.

### `R4-WEAK-GROUND-TRUTH`

- **Assumption:** Agmarknet validates video quotes.
- **Evidence against it:** DMI disclaims its own data's authenticity; in Aug 2025 the Assam marketing board was formally pulled up for markets submitting no data for a single day across Jun–Jul 2025. Validating noise against noise identifies nothing. The ground truth is trader invoices; Agmarknet is a third comparator. https://www.sentinelassam.com/topheadlines/assam-marketing-board-pulled-up-for-not-updating-data-on-agmarknet-portal

### `R5-COVERAGE-EDGE`

- **Assumption:** Agmarknet's Delhi coverage is bad enough that we beat it.
- **Evidence against it:** Unmeasured, and the entire product edge rests on it. The documented failure is Assam, not Delhi. M2 measures this. If Delhi coverage exceeds 90% of commodity-days with same-day reporting, the coverage advantage does not exist and only intraday timing remains.

### `R6-MOAT-MODEL-GAP`

- **Assumption:** The video corpus is the defensibility AND the model trains on Agmarknet history.
- **Evidence against it:** Both cannot be load-bearing. Log feature importance every training run and report the aggregate contribution of video-derived features; under 5% means the corpus does not defend the forecast.

### `R7-FORECAST-BAR`

- **Assumption:** Gradient boosting beats naive baselines on next-day F&V prices.
- **Evidence against it:** Daily fresh-produce prices are close to a random walk with weather shocks. With ~90 observations per series there is not enough history for tree models to generalise per-series, and none for deep learning. Baselines must always be computed and reported.

### `R8-YOUTUBE-TOS`

- **Assumption:** The corpus is both a legal risk and a defensible asset.
- **Evidence against it:** It cannot be both. An asset that cannot enter a data room is a private research seed, not a moat. See Gate 1 (YouTube ToS vs s.52 fair dealing).

### `R9-NOT-IP`

- **Assumption:** The dataset is proprietary IP.
- **Evidence against it:** Eastern Book Company v. D.B. Modak (SC of India, 2008) applies a "modicum of creativity" test and does not protect bare factual compilations. Prices are facts. Only the entity-resolution work involves the editorial judgment that could attract protection. https://lukeandluka.in/insights/eastern-book-company-v-db-modak-copyright-judicial-decisions-2008/

### `R10-QCOMM-SOURCING`

- **Assumption:** Buying quick-commerce feeds from data vendors is compliant.
- **Evidence against it:** Moves the terms-of-service breach one party away rather than removing it.

### `R11-RECORDER-CONFLICT`

- **Assumption:** Commission agents can be paid to report prices reliably.
- **Evidence against it:** They hold positions in the commodities they report — a structural conflict. Schema must record each observer's identity and whether they trade in what they report.

### `R12-RECORDER-ECONOMICS`

- **Assumption:** The platform scales like software.
- **Evidence against it:** Observer payroll scales linearly with mandi count, against a ₹6.6 crore NCR SAM. Emit an estimated monthly observer cost wherever a mandi is added.

### `R13-RANGE-MIDPOINT`

- **Assumption:** The midpoint of a quoted range is the representative price for modelling and deviation.
- **Evidence against it:** The data model deliberately refuses to collapse ranges at write time (price_low/price_high primary). But forecasting needs a scalar series and §5.2 computes deviation on the range midpoint, so "midpoint = the price" is an unavoidable modelling-layer assumption. Skew, thin tails, and quote-vs-trade spread all violate it. Raised by the lead engineer; not in the original 12.

