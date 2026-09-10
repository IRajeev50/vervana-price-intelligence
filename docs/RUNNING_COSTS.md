# RUNNING COSTS

Cost is a feature (Part 1.6). This file tracks the estimated **monthly** cost of every
component. **If cumulative fixed software cost passes ₹25,000/month, work stops and the
founder is told before continuing** (Gate 2 arithmetic).

Three cost stories are kept strictly separate because they behave differently:

1. **Fixed software/infra** — governed by the ₹25,000/mo ceiling.
2. **Variable messaging/compute** — per-use (WhatsApp, ASR, any LLM/embedding API).
3. **Observer payroll (R12)** — opex that scales linearly with mandi count; **not**
   software, **not** bounded by the ₹25k ceiling, and the real cost driver of the
   business against a ₹6.6 cr NCR SAM.

## 1. Fixed software/infra

| Component | Added at | 10 users | 100 users | 1,000 users | Notes |
|---|---|---|---|---|---|
| VPS (India region) | (deploy) | ₹1,200–1,800 | ₹2,500–3,500 | ₹5,000–7,000 | 2 GB → 4 GB → 8 GB. Runs app + Postgres + cron. |
| Domain | (deploy) | ~₹100 | ~₹100 | ~₹100 | Amortised annual. |
| Object storage (raw payloads, backups) | M2 | ~₹100 | ~₹300 | ~₹800 | Archived raw API/transcript payloads + nightly pg_dump. |
| CDN (dashboard static) | M3 | ₹0 | ₹0 | ~₹300 | Only meaningful at scale. |
| **Fixed total (est.)** | | **₹1,500–2,000** | **₹3,000–4,000** | **₹6,000–8,000** | Ceiling: ₹25,000. Margin ≈ 3×+. |

**M0 adds ₹0 fixed cost** (local dev + free GitHub Actions CI). The first real fixed cost
is the VPS at deploy time.

**M1 adds ₹0 fixed cost.** All new dependencies are libraries (sqlalchemy, alembic,
rapidfuzz, indic-transliteration, jellyfish, psycopg). The embedding/torch matching path
stays **deferred** (it would force a larger, costlier VPS); the shipped matchers are
lexical + phonetic, both light.

**M2 adds ₹0 fixed cost.** New dep is `httpx` (light). The Agmarknet API (data.gov.in) is
**free** under GODL-India. The only new *variable* item is negligible: outbound API calls
during the daily batch. Raw payloads are archived to local disk (`data/raw/`, git-ignored),
which counts toward the object-storage line already in the table above once deployed.

## 2. Variable messaging/compute (tracked, not yet incurred)

| Component | Added at | Basis | Note |
|---|---|---|---|
| WhatsApp Business API | M3 | Per conversation/message (Meta pricing) | Also a data-residency caveat (processed by Meta). |
| ASR for observer voice notes | M7 | Per audio-minute (metered API or small local model) | Batch; keep local if cost/residency demands. |
| Embeddings/LLM (optional entity-matching path) | M1 (optional) | Per token/request, or free if local | Only if the sentence-embedding matcher is chosen over rapidfuzz. |

## 3. Observer payroll (R12) — separate opex

| Driver | Basis | Note |
|---|---|---|
| Field observers | ~linear in mandi count × per-observer stipend | Emitted as an estimate wherever a mandi is added (M8). Dwarfs fixed software cost; the true constraint on unit economics. |

_Figures are estimates in INR/month and will be replaced with real invoices/quotes as
components are actually provisioned._
