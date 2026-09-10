# DATA DICTIONARY

Every table and column: its meaning, its source, and — crucially — **what it must never
be used for**. That last column is a first-class part of this product: the whole point is
to prevent misuse of prices that look comparable but are not.

## Conventions (apply to every table)

- **Money:** integer **paise** columns only (`*_paise`). Never floats.
- **Time:** timestamps are stored **UTC**, tz-aware (`UTCDateTime` rejects naive), displayed IST.
- **Provenance:** observed values carry the evidence that produced them; untraceable rows fail insertion.
- **Append-only where noted:** corrections insert a new row referencing `supersedes_id`; never updated in place.
- **Enums:** `VARCHAR + CHECK` on every engine (`native_enum=False`); values are constrained.

## `price_observation` — the single fact table (append-only)

| Column | Type | Meaning | Source | Must never be used for |
|---|---|---|---|---|
| `id` | int PK | Row id. | system | — |
| `commodity_id` / `variety_id` / `grade_id` / `market_id` | FK | What was priced, where. | registry | Resolving an unverified alias silently — resolution is a separate, reviewed step. |
| `source_class` | enum(4) | `quote_indicative` / `executed_summary` / `executed_trade` / `retail_offer`. | connector | **Averaging across classes** — the repository guard blocks this. A retail offer and a wholesale quote are not comparable. |
| `price_low_paise` / `price_high_paise` | int paise | The price **range** (primary; never collapsed). | source | Being reduced to a single number at write time. |
| `price_point_paise` | int paise, null | A single price, only when the source truly gave one. | source | Being invented from a range midpoint (that is a modelling choice — see `R13`). |
| `unit_raw` | text (immutable) | The unit as stated (e.g. "kg", "bag", "quintal"). | source | Being overwritten; it is the ground truth of what was quoted. |
| `canonical_price_paise_per_kg` | int paise, null | Derived ₹/kg. **NULL when weight unknown.** | derived | Being filled by guessing a bag weight (never hardcode 50 kg). |
| `unit_kg_equivalent` | Numeric, null | The conversion factor used. | `unit_convention` | — |
| `unit_conversion_confidence` | Numeric 0–1, null | Confidence in the conversion. | derived | Being ignored when surfacing canonical prices. |
| `source_url` | text (NOT NULL, non-empty) | Evidence link. | connector | Being blank — provenance is a DB constraint. |
| `raw_quote` | text (NOT NULL, non-empty) | The raw text/payload the price came from. | connector | Being discarded; it is the audit trail. |
| `observed_at` | UTCDateTime | When the price held (UTC). | source | Being stored naive, or as `exact` when it is estimated. |
| `time_basis` | enum(4) | `exact` / `estimated_window` / `single_daily_quote` / `daily_summary`. | connector | Making an estimated timestamp indistinguishable from a real one. |
| `observed_window_start` / `_end` | UTCDateTime, null | Bounds for `estimated_window`. | connector | — |
| `observer_id` | int, null | Field observer (M7); NULL for public sources. | observers | Aggregating without regard to observer independence (`R11`). |
| `supersedes_id` | FK self, null | The row this one corrects. | system | Counting a superseded row in any aggregate. |
| `supersede_reason` | text, null | Why the correction was made. | system | — |
| `created_at` | UTCDateTime | Insert time. | system | Being confused with `observed_at`. |

## Entity registry

### `commodity` / `variety` / `grade` / `market`
Canonical entities. `canonical_name` unique per commodity/market. `agmarknet_*_code` is
NULL until the M2 full-master import supplies real codes (M1 uses a hand-verified
bootstrap seed; **codes are not invented**).
- **Must never be used for:** treating a canonical name as legally protected content — per
  `R9`/EBC v. Modak these are facts; only the alias *verification* work is colourable IP.

### `alias`
| Column | Type | Meaning | Must never be used for |
|---|---|---|---|
| `alias_text` | text | A spoken/written/typed form. | Being assumed unique — many-to-many is intended (one text may map to several canonicals). |
| `alias_language` | text | e.g. `en`, `hi`, `hi-Latn`. | — |
| `alias_source_type` | enum(5) | `agmarknet_official` / `hindi_spoken` / `hinglish_transliteration` / `qcomm_sku_title` / `trader_colloquial`. | — |
| `canonical_type` + `canonical_id` | enum + int | Polymorphic pointer to the canonical entity. | Being trusted without repository validation (no single SQL FK spans four tables). |
| `confidence` | Numeric 0–1 | Match confidence. | — |
| `created_by` / `verified_by` / `verified_at` | text / text / UTCDateTime | Who proposed / verified it. | **Resolving on an unverified alias** — only `verified_by IS NOT NULL` aliases are the resolution surface. |

### `alias_review`
The human review queue. An automated match enters `pending`; promotion to `approved`
**requires a recorded reviewer** and verifies the alias. `method`/`score` record which
matcher proposed it and how confidently.
- **Must never be used for:** auto-approving matches without a human reviewer.

## `unit_convention` — bag-weight lookup
`(market_id?, commodity_id?, unit_raw) -> kg_equivalent`, with `source`, `confidence`,
`effective_from/to`. Most specific matching row wins.
- **Must never be used for:** inventing a weight when no row matches (leave canonical NULL).

## Not yet built (later milestones)
`ingest_run` (M2 connector metadata), `context_signal` (M4/M7 weather/diesel/festival),
observer identity + independence (M7).
