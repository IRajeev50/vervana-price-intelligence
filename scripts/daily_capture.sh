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

# Ensure schema + registry exist (idempotent), then run one live Delhi ingest.
uv run vervana db upgrade >/dev/null
uv run vervana registry seed >/dev/null
echo "[$(date)] live capture via Agmarknet 2.0 API (Delhi)"
uv run vervana ingest agmarknet --state Delhi
