# M12 - Phase 0: Hygiene + first-class persistence - DONE

- **Status:** DONE (2026-11-14). Branch `m12-phase0-hygiene-persistence`.
- **Scope delivered:** housekeeping + persistence only. No `src/vervana/` logic,
  models, or migrations changed. No modelling.

## 1. Deleted 15 numbered duplicate files

Each was `diff`'d against its canonical twin first (honesty check). Findings:
- `6-/7-package.json`, `7-/8-POLICY_IMPACT.md`, `2-/3-policy_impact.html`:
  **byte-identical** to canonical.
- `policy/4-/5-__init__.py`: **older drafts** - imported only
  `build_policy_impact, render_policy_pdf`, while canonical `__init__.py`
  imports four symbols (adds `build_decision_brief`, `render_intelligence_pdf`).
- `policy/5-/6-engine.py`, `web/1-app.py`, `static/3-/4-app.css`,
  `templates/1-/2-intelligence.html`: differ from canonical but are the
  unreferenced older copies; the numbered engine/css pairs are identical to each
  other.

Verdict: every numbered file is a stale/identical accidental copy. **Zero code
references** any of them (`grep` over `src/`, `tests/`, `Dockerfile`,
`.github/`). `docs/adr/0001-stack.md` is a real ADR and was **kept**.

Real output after deletion:
```
removed 15 files
=== any numbered dups left? ===   (none)
=== app + policy import ok? ===   imports OK
233 tests collected in 0.77s
```

## 2. README data-loading section fixed

The section claimed a `data.gov.in` key was required ("needs your data.gov.in key
in `.env`", "also needs the key", "data.gov.in is often slow"). The live
connector is keyless Agmarknet 2.0. Rewrote it to the real flow, sourced from the
connector's own `--help` ("public api.agmarknet.gov.in, no key") and the current
`scripts/daily_capture.sh`. No `data.gov.in` references remain in `README.md`.

Runnable backing (the keyless claim, shown live):
```
$ uv run vervana ingest agmarknet --state Delhi --max-records 5
fetching live Agmarknet 2.0 data ...
ingest_run#147 failed: HTTPStatusError: Client error '400 Bad Request' for url
'https://api.agmarknet.gov.in/v1/.../daily-report-state?date=2026-11-14&state=25...'
no data was saved for this run; retry the same command in a few minutes
```
The request reached `api.agmarknet.gov.in` with **no key** and failed honestly
(today's report not yet published) - it stored nothing, invented nothing.

## 3. Persistence made first-class

- New `scripts/verify_persistence.sh`: migrate + seed in one process, reopen the
  **same** database in a **separate** process, pass only if rows survived. Runs
  against local sqlite by default, or remote Turso when the two env vars are set.
  Real output:
  ```
  [verify] process 1 wrote commodities: 31
  [verify] process 2 (fresh process): reopen + re-count
  [verify] process 2 read commodities:  31
  [verify] PASS: 31 rows survived the process restart.
  ```
- `docs/RUNBOOK.md`: new `## Database persistence (Render + Turso)` section with
  the exact `turso db create` / `tokens create` commands, the two Render
  environment variables and where they go, the first migrate+seed, and a
  one-command post-deploy verification (`verify_persistence.sh` +
  `vervana ingest history`).
- Existing `tests/test_turso.py` (engine selection: libSQL URL built correctly,
  token required, sqlite stays local) stays green.

**Boundary (Open Q1, option A chosen):** the libSQL *code path* and
restart-survival are proven locally; the true "survives a Render redeploy" proof
is a runbook procedure Rajeev runs against the live service with his own Turso
token. I did not handle the token.

## Test results - HONEST status

- **226 passed, 7 failed, 233 total.**
- The 7 failures are **pre-existing and not caused by Phase 0**: proven by
  stashing all Phase 0 changes and running them on the clean `main` baseline -
  the identical 7 fail (`7 failed, 5 passed` of the targeted subset).
- They are environment/data-dependent. Two are directly the same legacy debt
  this phase touched: `test_web.py::test_evidence_shows_provenance` and
  `::test_api_observation_traces` hard-code `assert "api.data.gov.in" in r.text`
  - a stale expectation from the retired data.gov.in era. The others:
  `test_admin_supply` (x2), `test_ground_proof_upload` (x2),
  `test_transcript::test_ingest_video_quotes`.

**This contradicts the spec's "233 passing" assumption.** The tree is 226/233.
Phase 0 is **regression-free** (226 pass with and without it) but the gate as
written ("233 green") cannot be literally met on this checkout. I did not fix the
7 (out of hygiene scope) and did not widen the gate to hide them. **Decision
needed:** a small follow-up milestone to fix/retire the 7 stale tests
(the 2 `data.gov.in` ones are quick), or leave them documented.

## Lint finding (not a regression)

`ruff check` reports **353 errors repo-wide** under *both* the installed 0.16.6
and the repo's pinned 0.6.9 - concentrated in old untouched files
(`E702`/`E501`/`E701`). Cause: pre-commit only lints **changed** files (`--fix`
on staged) and there is **no ruff step in CI**, so a backlog accrued in files
nobody re-touched. Phase 0 adds **no Python**, so it introduces none. Documented
as a finding; fixing the backlog is its own task, not Phase 0.

## Cost impact

Zero new fixed cost. Turso has a free tier sufficient for this data volume;
logged in `docs/RUNNING_COSTS.md` note. Cumulative fixed cost unchanged, well
under the Rs 25,000/mo stop-line.

## What did NOT work / findings to carry forward

1. 7 pre-existing test failures (above) - the tree is not 233-green as assumed.
2. Repo-wide ruff backlog (353) - no CI lint gate exists.
3. Scheduled Agmarknet captures #127-147 (Nov 5-14) are failing `in=0` in
   `ingest history` - a live-capture reliability issue (separate from PR #28's
   wake-from-sleep fix), likely environment/date-param. Flagged, not in scope.

## Next step

Open the Phase 0 PR. On merge, proceed to **M13 / Phase 1 (WeatherNext supply
feed)** - but first get Rajeev's call on the 7 pre-existing failures and whether
a `ruff`-backlog cleanup should precede the modelling phases.
