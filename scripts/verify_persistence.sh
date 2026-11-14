#!/bin/bash
# Persistence smoke test: prove data survives a PROCESS RESTART against the
# configured database (M12 Phase 0).
#
# Why this exists: the hosted site has lost its database to Render's ephemeral
# disk repeatedly. The fix is Turso (remote libSQL) in production; this script
# proves the survival mechanism locally - migrate + seed in one process, then
# reopen the SAME database in a SEPARATE process and confirm the rows are still
# there. Point it at Turso (export VERVANA_TURSO_DATABASE_URL + _AUTH_TOKEN) to
# run the identical check against the remote database.
#
# Usage:
#   bash scripts/verify_persistence.sh                 # local sqlite temp file
#   VERVANA_TURSO_DATABASE_URL=... VERVANA_TURSO_AUTH_TOKEN=... \
#     bash scripts/verify_persistence.sh               # remote Turso
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# When no Turso env is set, use a throwaway local sqlite file so we never touch
# vervana.dev.sqlite3. When Turso IS set, the engine picks it up automatically
# and this variable is ignored.
if [[ -z "${VERVANA_TURSO_DATABASE_URL:-}" ]]; then
  TMP_DB="$(mktemp -t vervana_persist_XXXX).sqlite3"
  export VERVANA_DATABASE_URL="sqlite:///${TMP_DB}"
  trap 'rm -f "${TMP_DB}" "${TMP_DB}-wal" "${TMP_DB}-shm"' EXIT
  echo "[verify] local sqlite: ${TMP_DB}"
else
  echo "[verify] remote Turso: ${VERVANA_TURSO_DATABASE_URL}"
fi

echo "[verify] process 1: migrate + seed"
uv run vervana db upgrade >/dev/null
uv run vervana registry seed >/dev/null

# Count seeded commodities in this first process.
BEFORE="$(uv run python -c '
from vervana.db.engine import session_scope
from vervana.models.entities import Commodity
from sqlalchemy import select, func
with session_scope() as s:
    print(s.execute(select(func.count(Commodity.id))).scalar_one())
')"
echo "[verify] process 1 wrote commodities: ${BEFORE}"

# ---- SEPARATE process: open the same database fresh and re-count. ----
echo "[verify] process 2 (fresh process): reopen + re-count"
AFTER="$(uv run python -c '
from vervana.db.engine import session_scope
from vervana.models.entities import Commodity
from sqlalchemy import select, func
with session_scope() as s:
    print(s.execute(select(func.count(Commodity.id))).scalar_one())
')"
echo "[verify] process 2 read commodities:  ${AFTER}"

if [[ "${BEFORE}" -gt 0 && "${BEFORE}" == "${AFTER}" ]]; then
  echo "[verify] PASS: ${AFTER} rows survived the process restart."
  exit 0
fi
echo "[verify] FAIL: before=${BEFORE} after=${AFTER} (data did not survive)."
exit 1
