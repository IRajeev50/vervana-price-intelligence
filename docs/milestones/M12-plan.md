# M12 - Phase 0: Hygiene + first-class persistence - PLAN

- **Status:** PLANNED (2026-11-14). No code until Rajeev's go.
- **Trigger:** Start of the four-phase weather/band/flood build. Phase 0 clears
  accumulated hygiene debt and ends the repeated loss of the hosted database to
  Render's ephemeral disk, so later phases build on a clean, durable base.
- **Scope rule that outranks everything (inherited):** nothing modelling-related
  ships here - Phase 0 is housekeeping + persistence only. No new signals, no
  forecast changes.

## Grounding (verified in the repo today, not assumed)

- HEAD `5c75394` on `main`; last milestone shipped is **M11**, so this is **M12**.
- **233 tests collected** (`pytest --collect-only` -> "233 tests collected").
  Matches the spec's claim. The gate is: still 233+ green after Phase 0.
- **Numbered duplicate files that are tracked** (confirmed via `git ls-files`):
  - `6-package.json`, `7-package.json`  (canonical `package.json` exists)
  - `7-POLICY_IMPACT.md`, `8-POLICY_IMPACT.md`  (canonical `POLICY_IMPACT.md` exists)
  - `src/vervana/policy/4-__init__.py`, `5-__init__.py`, `5-engine.py`, `6-engine.py`
    (canonical `__init__.py`, `engine.py` exist)
  - `src/vervana/web/1-app.py`  (canonical `app.py` exists)
  - `src/vervana/web/static/3-app.css`, `4-app.css`  (canonical `app.css` exists)
  - `src/vervana/web/templates/1-intelligence.html`, `2-intelligence.html`,
    `2-policy_impact.html`, `3-policy_impact.html`  (canonical versions exist)
  - **NOT a duplicate, explicitly kept:** `docs/adr/0001-stack.md` (a real ADR;
    4-digit prefix only matched the search pattern).
- **No code references the numbered files.** `grep` across `src/`, `tests/`,
  `Dockerfile`, `.github/` found zero imports/includes/`url_for`/template
  references to any `N-<name>`. Deletion is therefore expected to be inert - the
  plan still re-confirms this per file before removing it.
- **README still documents the retired flow:** lines ~54 and ~100 of `README.md`
  describe the `data.gov.in` key + "resource" ingest ("needs your data.gov.in
  key in `.env`", "data.gov.in is often slow"). The live connector is
  `connectors/agmarknet.py` (Agmarknet 2.0, keyless) - its docstring is the truth.
- **Turso path already wired in code:** `config.py` (`turso_database_url`,
  `turso_auth_token`), `db/engine.py` (builds `sqlite+libsql://...?secure=true`
  with `auth_token`), and `tests/test_turso.py` exist. What is missing is a
  proven end-to-end survival procedure and the exact Render steps.
- `docs/RUNBOOK.md` exists with failure scenarios but **no Render+Turso
  persistence section**.

## Scope (three work items + gate)

### 1. Delete the numbered duplicate files
- For **each** numbered file: `diff` it against its canonical twin first.
  - If identical or clearly the stale/older copy -> delete.
  - If a numbered file contains content the canonical one lacks -> **STOP and
    flag it** in this plan's follow-up, do not silently delete. (Honesty rule:
    a duplicate might be the accidentally-newer copy.)
- Re-run the reference grep after deletion; `git grep` must stay clean.
- `package.json` oddity (a JS manifest in a Python repo) is **left as-is** beyond
  removing the numbered copies - out of scope to investigate here.

### 2. Fix the README data-loading section
- Rewrite the `data.gov.in` / "resource" paragraphs to describe the **Agmarknet
  2.0 keyless** flow, sourced from `connectors/agmarknet.py`'s own docstring and
  the working `vervana ingest agmarknet` command. No invented commands - every
  command in the README will be one I actually run and show output for.

### 3. Make persistence first-class
- **Offline code-path proof (what I can prove without secrets):** a scripted
  cycle against a local libSQL-format file - `db upgrade` -> `registry seed` ->
  a small ingest -> close the process -> reopen -> assert the rows are still
  there. Plus `tests/test_turso.py` stays green. This proves data survives a
  **process restart** through the libSQL engine path.
- **Hosted survival (what needs Rajeev's secrets, documented not executed):** a
  new `## Database persistence (Render + Turso)` section in `docs/RUNBOOK.md`
  with the exact env vars (`VERVANA_TURSO_DATABASE_URL`,
  `VERVANA_TURSO_AUTH_TOKEN`), where they go in the Render dashboard, the
  `turso db create` / `turso db tokens create` commands, and a **one-command
  verification** (`vervana db current` / a row-count check) to run after deploy.
  I will **not** handle the Turso token myself - that is Rajeev's secret and the
  Render change is his to make; Phase 0 gives him the exact runbook, not my
  hands on his credentials.

### Gate (all must hold for the PR)
- Clean tree: no `N-*` numbered duplicates remain; `git status` clean.
- **233+ tests green**, offline, no network.
- `ruff check` clean.
- README data-loading section matches the real Agmarknet 2.0 commands (shown
  running).
- RUNBOOK has the Render+Turso persistence section with exact steps.
- One PR, `docs/milestones/M12-done.md` written with real output.

## Files touched (expected)

- **Deleted:** the 15 numbered duplicate files listed above.
- **Edited:** `README.md` (data-loading section), `docs/RUNBOOK.md` (new
  persistence section).
- **Added:** `docs/milestones/M12-done.md` (after build).
- **Possibly added:** a tiny `scripts/verify_persistence.sh` (or a doc-only
  procedure) for the restart-survival check - decided at build time, kept out of
  the serving path either way.
- **No** changes to `src/vervana/` logic, models, or migrations in Phase 0.

## Tests

- No new modelling tests. Existing 233 must stay green.
- If I add a persistence helper script, it is covered by being run and shown, not
  by a network test (ground rule 3: no network in the suite).

## Open questions (genuine forks - need a decision before/at build)

1. **Hosted verification boundary.** I can prove restart-survival of the libSQL
   *code path* locally and write the exact Render+Turso runbook, but a true
   "survives a Render redeploy" proof needs your Turso DB + token on the live
   service. **Plan:** I document + hand you the one-command check; you run it
   against the live service. Acceptable, or do you want to provision a throwaway
   Turso DB whose token you paste so I verify end-to-end locally against *remote*
   Turso? (I'd still never commit the token.)
2. **Any numbered file that is actually newer than its canonical twin.** If a
   `diff` shows the numbered copy has unique, wanted content, I stop and show you
   rather than delete. Default assumption: they are stale accidents (consistent
   with "accidentally committed"), safe to remove.

## Explicitly out of scope (Phase 0)

- WeatherNext, Flood Hub, the quantile band, GRN import - all later phases.
- Touching forecast/kill logic or `data/backtests/latest.json`.
- Investigating why a `package.json` exists in a Python repo (noted, deferred).
- Setting anything in the Render dashboard on your behalf.
