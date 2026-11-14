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

## Database persistence (Render + Turso)

**The problem.** The hosted app runs on Render's free tier, whose disk is
**ephemeral** — it is wiped on every deploy and on container restarts. A SQLite
file (`vervana.dev.sqlite3`) therefore does **not** survive a redeploy; the hosted
database has been lost this way repeatedly. The fix is to point production at
**Turso** (remote libSQL), which lives outside the container.

**How the code chooses the database** (`src/vervana/db/engine.py`): when **both**
`VERVANA_TURSO_DATABASE_URL` and `VERVANA_TURSO_AUTH_TOKEN` are set, the engine
builds `sqlite+libsql://<host>?secure=true` and talks to Turso. If only one is
set it raises (`must be set together`) — fail loud, never silently fall back to a
disposable local file in production. With neither set it uses local SQLite (dev).

### One-time Turso setup
```bash
# Install the Turso CLI, then:
turso auth login
turso db create vervana                      # creates a libSQL database
turso db show vervana --url                   # -> libsql://vervana-<org>.turso.io
turso db tokens create vervana                # -> the auth token (store securely)
```

### Set the env vars on Render (the step that ends the data loss)
In the Render dashboard → the service → **Environment** → add:

| Key | Value |
| --- | --- |
| `VERVANA_TURSO_DATABASE_URL` | `libsql://vervana-<org>.turso.io` (from `db show`) |
| `VERVANA_TURSO_AUTH_TOKEN`   | the token from `db tokens create` |

Save → Render redeploys. These are **secrets**: they live only in Render's
environment, never in the repo or `.env` committed to git (`.env` is git-ignored;
`.env.example` lists the keys with empty values).

### First migrate + seed against Turso
Once the env vars are set (locally export the same two to target Turso from your
machine, or let the deploy's start command run them):
```bash
uv run vervana db upgrade        # creates the schema in Turso
uv run vervana registry seed     # loads reference commodities/markets
```

### Verify persistence survives a restart (one command)
```bash
# Local sqlite mechanism check (no secrets needed):
bash scripts/verify_persistence.sh

# Against the real remote database:
VERVANA_TURSO_DATABASE_URL=libsql://vervana-<org>.turso.io \
VERVANA_TURSO_AUTH_TOKEN=<token> \
  bash scripts/verify_persistence.sh
```
It migrates + seeds in one process, reopens the **same** database in a **separate**
process, and passes only if the rows survived. After a Render redeploy, confirm the
hosted data is intact:
```bash
uv run vervana ingest history    # the run log should still show past runs
```
If `ingest history` is empty right after a deploy, the Turso env vars are missing
or mistyped — the app fell back to the ephemeral local file. Re-check the two keys.

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
