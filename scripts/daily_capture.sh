#!/bin/bash
# Daily Agmarknet snapshot capture (R5 coverage-over-time).
#
# The connector pulls the official Agmarknet 2.0 public API (api.agmarknet.gov.in),
# which is keyless - no .env entry or API key required. The old data.gov.in resource
# (9ef84268) went stale in Nov 2025 and is no longer used. Each run records an
# ingest_run, which is the coverage history we need to answer R5.
set -euo pipefail

# Repo root is derived from this script's location, so the script works wherever the
# repo is cloned.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"
export PATH="$HOME/.local/bin:$PATH"

# Wait for the network to be reachable before ingesting. launchd fires missed
# StartCalendarInterval jobs immediately on wake-from-sleep, when Wi-Fi/DNS may not
# be up yet - the connector then fails DNS resolution (EAI_NONAME) and every retry
# lands inside that ~1-minute window. Poll the API host until it answers (up to
# ~2 min); if it never does, skip WITHOUT recording a failed run.
wait_for_network() {
  # No -f: we only care that the host is REACHABLE (DNS resolves + TCP connects).
  # curl returns 0 for any HTTP response (a 404 from the root still means "up"),
  # and non-zero (6/7) only on a DNS or connection failure - exactly what we wait out.
  for _ in $(seq 1 24); do
    if curl -sS -o /dev/null --max-time 5 "https://api.agmarknet.gov.in" 2>/dev/null; then
      return 0
    fi
    sleep 5
  done
  return 1
}

if ! wait_for_network; then
  echo "[$(date)] network/DNS not ready after 2 min (likely just woke from sleep) - skipping this capture, no failed run recorded"
  exit 0
fi

# Ensure schema + registry exist (idempotent), then run one live Delhi ingest.
uv run vervana db upgrade >/dev/null
uv run vervana registry seed >/dev/null
echo "[$(date)] live capture via Agmarknet 2.0 API (Delhi)"
uv run vervana ingest agmarknet --state Delhi
