# M10 - Product UI/UX redesign + intelligence portfolio & outlook calendar - PLAN

## Goal

Make the web app feel like a coherent agricultural-intelligence product without
changing what it says: every factual string, disclaimer, honesty label and
safety gate stays. Add the two intelligence surfaces Rajeev asked for:

1. A crop portfolio (`/intelligence`) - every configured crop with its honest
   horizon, latest saved verdict, price-pressure direction, confidence,
   observed/simulated/missing coverage and derived alerts.
2. A date-based outlook calendar (`/intelligence/history`) - saved outlooks by
   the date they were actually made; day views serve ONLY stored records.

## Non-negotiables (carried from M0-M9)

- No lookahead: historical dates never recompute; they show the append-only
  record, unedited, with its as-of timestamp.
- observed / simulated / missing labels survive every render path (live build
  AND the stored-JSON round-trip).
- Simulated inputs still cap confidence at 0.35; the R7 forecast kill gate is
  untouched; the DMI disclaimer + GODL-India attribution stay on every page.
- Region filtering narrows the displayed input table only; the chain stays
  commodity-level (producer-group feeds are not connected - said out loud).
- No decorative charts that imply data we do not have. The only quantitative
  visual is the confidence meter, which renders the stored confidence value.
- Localhost-only; no paid dependencies; no public deployment.

## Surfaces

- Design system in `src/vervana/web/static/app.css` (tokens, sidebar shell,
  stat cards, callouts, pills, chain stepper, calendar grid, responsive +
  accessibility rules).
- All 11 existing templates rebuilt on the system.
- New routes: portfolio rework, `GET /intelligence/history[?month&commodity]`,
  `GET /intelligence/history/<day>`, `GET /intelligence/record/<id>`,
  `POST /intelligence/<commodity>/save`, `GET /api/intelligence/records/<id>`.
- Tests: `tests/test_intelligence_views.py` (9 tests).
