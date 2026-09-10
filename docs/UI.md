# UI design system (M10)

The web app is a document of record, not a dashboard toy. The design system
exists to make trust states scannable: **what is observed, what is simulated,
what is missing, and what the platform concluded - with its as-of timestamp.**

## Principles

1. **Status colour is evidence colour.** Green/amber/grey mean observed /
   simulated / missing (or ok / warn / neutral for run health). Colour is never
   decorative.
2. **No fabricated shape.** No charts, sparklines or maps that imply data the
   platform does not hold. The single quantitative visual is the confidence
   meter, which renders the stored confidence value (amber when capped by
   simulated inputs).
3. **Every page says when and where its numbers came from.** As-of timestamps
   (IST for records, UTC for build times), evidence links, and the DMI +
   GODL-India footer on every page.
4. **Empty is an answer.** Empty states name what is missing and how it gets
   filled; they never show placeholder data.
5. **Accessible by default.** Landmark structure, skip link, `aria-current` on
   navigation, labelled form fields, 40px minimum touch targets, visible focus
   rings, `prefers-reduced-motion` respected.

## Tokens (`src/vervana/web/static/app.css`)

- Surfaces: `--bg #f5f7f3`, `--surface #fff`, sunken `#f0f3ee`, lines `#e2e8e0`.
- Ink: `--ink #1b2420`, muted `#627165`.
- Brand evergreen scale `--brand-900..50` (sidebar + primary actions).
- Status: ok `#177245`, warn `#96610a`, danger `#b42318`, neutral `#5c6862`,
  each with a soft background and border tone.
- Type: system stack; 24/17/15 headings; `tabular-nums` for figures.
- Layout: 248px sidebar, 1160px max content, mobile breakpoint 980px.

## Components

`.stat-grid`/`.stat` (KPIs), `.callout--ok|warn|danger|info` (verdicts and
notices), `.pill--observed|simulated|missing|ok|warn|danger|info` (status),
`.meter` (confidence), `.dir--up|down|neutral|na` (signal direction),
`.chain` (reasoning stepper), `.table-wrap` + `table.data` (scroll-x tables),
`.filters` + `.field` (filter bars), `.empty` (empty states), `.kv`
(provenance grid), `.cal` (outlook calendar), `.portfolio` + `.crop-card`.

## Intelligence surfaces

- `/intelligence` - crop portfolio (status, horizon, direction, confidence,
  coverage, alerts per crop).
- `/intelligence/history` - outlook calendar; day views serve only the
  append-only record store. The no-lookahead rule is stated on the page.
- `/intelligence/record/<id>` - a saved outlook, rendered unedited.
- `/intelligence/<commodity>?region=...` - region filter on the input table
  only; the reasoning chain is commodity-level. Producer-group feeds are not
  connected yet, and the page says so.
