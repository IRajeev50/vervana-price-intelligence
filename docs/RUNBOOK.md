# RUNBOOK

What to do when something breaks. Written for a junior developer operating a single VPS.

> **Skeleton.** Scenarios are filled in as the systems they describe are built. The
> structure is fixed now so each milestone adds its operational notes here.

## Scenarios

### An ingest run fails
_(filled in M2, once the Agmarknet connector and `ingest_run` tracking exist.)_
Planned shape: check the latest `ingest_run` row for status + rejection reasons →
inspect stored raw payload → re-run the idempotent daily command → escalate if the
source API is down (data loss must not occur; raw payloads are stored before parsing).

### An API key expires (e.g. data.gov.in)
_(filled in M2.)_ Planned shape: symptom (auth errors in ingest logs) → rotate the key in
the deploy environment (never in the repo) → re-run.

### A parser starts flagging everything
_(filled in M2/M6.)_ Planned shape: a sudden spike in flagged/rejected rows usually means
an upstream format change or a bad range-sanity bound → do **not** relax flagging to make
it pass → inspect samples → fix the parser or the bounds → re-run against stored raw
payloads.

### Restore from backup (VPS lost)
_(filled at deploy.)_ Planned shape: provision a new Indian-region VPS → `docker compose
up` → restore the latest nightly `pg_dump` from Indian object storage → verify row counts
against the last `ingest_run`.

## Daily Agmarknet capture (R5 coverage-over-time)

A macOS **launchd** agent runs the snapshot capture **3×/day at 10:00, 15:00, 20:00 IST**
to measure whether/when Delhi appears in Agmarknet's daily feed. It only runs when the Mac
is awake around those times.

- **Script:** `scripts/daily_capture.sh` (curl-based; works even where httpx is blocked).
- **Agent:** `~/Library/LaunchAgents/in.vervana.dailycapture.plist`.
- **Data it builds:** `vervana.dev.sqlite3` (an `ingest_run` per capture) and
  `data/coverage_probe.csv` (`captured_at_utc,total_rows,delhi_rows,delhi_markets` — the
  Delhi count is independent of alias resolution, so it is the real signal).
- **Logs:** `logs/capture.log`, `logs/capture.err.log`.

| Task | Command |
|---|---|
| Run one capture now | `bash scripts/daily_capture.sh` |
| See capture history | `uv run vervana ingest history` |
| See the Delhi probe timeline | `cat data/coverage_probe.csv` |
| Is the agent loaded? | `launchctl list \| grep vervana` |
| **Stop the daily capture** | `launchctl unload -w ~/Library/LaunchAgents/in.vervana.dailycapture.plist` |
| Re-enable it | `launchctl load -w ~/Library/LaunchAgents/in.vervana.dailycapture.plist` |
| Remove it entirely | unload (above), then `rm ~/Library/LaunchAgents/in.vervana.dailycapture.plist` |

**Reading the result:** once `data/coverage_probe.csv` has a week+ of rows, if `delhi_rows`
is consistently 0 at all three times, Agmarknet does not carry Delhi same-day (a real
coverage/timeliness gap — but also means we cannot source Delhi from Agmarknet). If
`delhi_rows` jumps up only at the 20:00 capture, that is a *timing* effect (Delhi reports
late in the day). Either outcome resolves R5; record it in the R5 code tag and M2-done.

## Everyday commands

| Task | Command |
|---|---|
| Health check | `uv run vervana healthcheck` |
| Run tests | `make test` |
| Regenerate risk register | `make risks` |
| Start/stop local stack | `make up` / `make down` |
