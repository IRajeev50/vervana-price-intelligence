# M3 — Serving layer · DONE

- **Status:** COMPLETE. A usable web platform + JSON API, running on **real live data**.
- **Date:** 2026-09-10. **Built because** the founder asked for a usable platform; the
  reordered plan (Part 6) puts serving ahead of forecasting for exactly this reason.

## Definition of done vs actual

| Criterion (Part 6) | Result |
|---|---|
| API + minimal dashboard + (WhatsApp digest) | ✅ FastAPI + server-rendered dashboard + JSON API. WhatsApp digest deferred (needs a persona decision + Meta API; OPEN_QUESTIONS #4/#7). |
| Every displayed price links to its evidence, shows source class + confidence | ✅ every `/prices` row → `/evidence/{id}` showing source_url, the raw source record, conversion factor, timestamps, and a `/api/observations/{id}` link. |
| I can click any number and reach the API row it came from | ✅ verified in-browser: price → evidence page → `/api/observations/{id}` JSON. |
| Ship early | ✅ shipped before forecasting, on real data. |

## Made it genuinely usable (not empty)
The Delhi feed is empty (the R5 finding), so to make the platform real I bootstrapped the
registry from **Agmarknet's own official vocabulary** (`registry bootstrap`) — legitimate
per "seed from official Agmarknet lists" — and re-ingested the live snapshot:
**5,735 real price observations, 127 commodities, 264 markets.** The platform now browses
real national mandi prices while monitoring Delhi coverage.

## Real output (verified in-browser this session)
- **Dashboard:** 5,735 observations · 127 commodities · 264 markets · last ingest ok
  (5,735 / 6,043) · Delhi 0 rows.
- **Prices:** e.g. Maize @ Chintapally APMC ₹1,500–2,500/quintal → **₹20.00/kg**
  (range preserved, quintal→kg correct, `executed_summary` pill, confidence 0.8).
- **Evidence #1:** full provenance incl. the exact data.gov.in record and source URL.
- **Coverage:** honest NO-DATA verdict for Azadpur/Keshopur + the daily Delhi probe.
- **63 offline tests pass** (6 new web tests via TestClient — no network); lint clean.

## What's in it
- `src/vervana/web/app.py` + Jinja templates: Dashboard, Prices (filter + evidence),
  Evidence, Coverage (R5 + probe), Review (approve with recorded reviewer), Ingest history.
- JSON API: `/api/stats`, `/api/observations/{id}`.
- **Every page carries the DMI accuracy disclaimer + GODL-India attribution** (Part 7).
- Confidence = source-reliability × unit-conversion-confidence, shown honestly as partial
  (cross-source agreement not yet computed — §5.4 to complete later).
- CLI `vervana serve`; `.claude/launch.json` for the preview.

## Deviations / notes
- **WhatsApp digest deferred** — it needs the persona decision (R2, who's the customer)
  and the Meta API (residency caveat). The provenance-linked data layer it would send is
  done; wiring the channel is a small follow-up once the persona is set.
- `registry bootstrap` auto-verifies names from the official Agmarknet feed as
  `agmarknet_official` (they are the authority, not an automated guess) — consistent with R9
  (only *editorial* alias judgment is the protected asset).

## Follow-up completed (2026-09-10): persona + digest + quick-commerce

Founder set the persona: **HoReCa buyers + quick-commerce operators** (resolves R2 →
RESOLVED). Built the two pending pieces:

- **Quick-commerce retail ingest** (Part 4.5) — `QuickCommerceConnector` with the
  **compliant manual-panel CSV path only**; the vendor-feed `fetch_raw` is a stub that
  *refuses to run*, carrying `R10`. **No scraper** (Part 7). Pack prices normalised to
  ₹/kg while pack size / MRP / selling price / fees are kept separately
  (`retail_offer_detail`). Sample: 6 rows imported → `retail_offer` observations.
- **HoReCa procurement digest** (the WhatsApp piece) — `vervana digest` and `/digest`
  render the **wholesale-vs-retail spread** for a basket, e.g. *Tomato: wholesale ₹28/kg |
  retail ₹58/kg (Blinkit) → retail ₹30/kg above wholesale (+107%)*. The two are shown
  side by side and **never blended** (guard enforced; a test proves averaging them still
  raises). Every line carries an evidence id, source class, and confidence (Part 7). The
  digest honestly labels wholesale as "national latest, not Delhi" until the R5 capture
  yields Delhi data.
- Confidence unified in `vervana/confidence.py` (source reliability × conversion conf ×
  agreement=1.0-for-now, labelled partial per §5.4).
- **67 offline tests pass; lint clean.** Risk register: 5 live tags (R2 RESOLVED; R4, R5,
  R9, R10 PENDING).

**Still deferred:** actually *sending* the digest to WhatsApp numbers needs the Meta
Business API (a data-residency decision, OPEN_QUESTIONS #7) and is a permissioned send —
the message *content* is done; wiring the channel is the remaining step.

## Cost impact
₹0 fixed (FastAPI/uvicorn/Jinja are libraries; served from the same VPS as the batch).

## Next
Options: complete the WhatsApp digest once the persona is chosen; let the R5 capture
accumulate a week and record the verdict; or M4 (forecasting harness — likely to under-
perform per R7, but the harness + public log are the deliverable).
