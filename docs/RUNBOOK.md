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

## Everyday commands

| Task | Command |
|---|---|
| Health check | `uv run vervana healthcheck` |
| Run tests | `make test` |
| Regenerate risk register | `make risks` |
| Start/stop local stack | `make up` / `make down` |
