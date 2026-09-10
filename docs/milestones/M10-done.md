# M10 - Product UI/UX redesign + intelligence portfolio & outlook calendar - DONE

- **Status:** COMPLETE. 126 offline tests pass (9 new), ruff lint + format clean.
- **Date:** 2026-09-10.

## What was built

- **Design system** (`src/vervana/web/static/app.css`): evergreen/slate token
  palette; status colour reserved for evidence states (observed = green,
  simulated = amber, missing = grey); tabular numerals for all figures;
  4px-spacing scale; focus-visible rings; skip link; reduced-motion support.
- **App shell**: grouped sidebar navigation (Overview / Research / Operations)
  with `aria-current="page"`, collapsing to a top bar with a no-JS `<details>`
  menu under 980px. Footer keeps the DMI disclaimer and GODL-India attribution
  verbatim on every page.
- **Pages rebuilt**: Dashboard (stat grid + callouts), Prices (labelled filter
  bar, numeric-aligned tables with scroll-x on mobile), Benchmark, HoReCa digest
  (chat-style preview), Coverage, Forecast log (kill-gate banner + stat cards),
  Evidence (provenance key-value grid), Review, Ingest. Empty states everywhere
  say what is missing and why instead of implying data.
- **Crop portfolio** (`/intelligence`): per-crop card with honest horizon,
  latest saved verdict, price-pressure direction chip, confidence meter
  (amber when capped by simulated inputs), observed/simulated/missing coverage,
  as-of timestamp (IST) and derived alerts; crops with no saved analysis get an
  explicit empty state, never a fabricated summary.
- **Outlook calendar** (`/intelligence/history`): month grid with per-day saved
  counts, month navigation, crop filter; day view lists the records made on
  that date. Empty days state that nothing was recorded. Past dates serve ONLY
  the append-only `intelligence_report` store - the platform never recomputes
  what it "would have said" (no lookahead).
- **Saved outlook view** (`/intelligence/record/<id>`): renders the stored JSON
  unedited with a "Historical snapshot" banner, as-of IST timestamp and API
  link; the honesty labels survive the storage round-trip (tested).
- **Save action**: `POST /intelligence/<commodity>/save` builds the current
  outlook and appends it to the audit log (same code path as the CLI).
- **Region filter** on the outlook page narrows the input-signals table, with an
  on-page note that the chain uses all regions and producer-group feeds are not
  connected.
- **API**: `GET /api/intelligence/records/<id>` returns the stored record
  (commodity, made_at, counts, confidence, full report JSON).
- Docs: `docs/UI.md` (design system reference); this milestone file.

## What did not change

- Server-side architecture (FastAPI + Jinja + SQLite/Postgres), all routes and
  their factual wording, the forecast kill criterion (R7), the honesty gates,
  and localhost-only behaviour. No new dependencies; no schema migration was
  needed (the M9 append-only table already carried everything).

## Verification

- `uv run pytest` - 126 passed (117 before + 9 new view tests).
- `uv run ruff check .` and `uv run ruff format --check .` - clean.
- Every page screenshotted at 1440px and 390px (Chrome headless) and visually
  inspected: dashboard, prices, benchmark, digest, coverage, forecast,
  portfolio, calendar, calendar-day, outlook, saved record, region filter,
  review, ingest, evidence.
