#!/bin/bash
# Daily Agmarknet snapshot capture (R5 coverage-over-time).
#
# Pulls the FULL current-daily snapshot (all states, paginated) and ingests it. We do
# NOT filter to Delhi at the API, so the capture is robust to state-label quirks:
# whatever resolves to a seeded Delhi market is accepted; everything else is counted as
# rejected. Every run — even one with zero Delhi rows — records an ingest_run, which is
# the coverage history we need to answer R5.
#
# Uses curl (works everywhere, incl. restricted shells) then `vervana ingest
# agmarknet-file`. On a normal host `vervana ingest agmarknet` (httpx) works too.
set -euo pipefail

PROJECT_DIR="/Users/rajeevsingh.1/Mandi bhav"
RESOURCE="9ef84268-d588-465a-a308-a864a43d0070"
cd "$PROJECT_DIR"
export PATH="$HOME/.local/bin:$PATH"

if [ ! -f .env ]; then echo "no .env (need VERVANA_DATA_GOV_IN_API_KEY)"; exit 1; fi
KEY=$(grep '^VERVANA_DATA_GOV_IN_API_KEY=' .env | cut -d= -f2)
if [ -z "$KEY" ]; then echo "VERVANA_DATA_GOV_IN_API_KEY is empty in .env"; exit 1; fi

TS=$(date -u +%Y%m%dT%H%M%SZ)
RAW_DIR="data/raw/agmarknet"
mkdir -p "$RAW_DIR" logs
COMBINED="$RAW_DIR/snapshot_${TS}.json"

# Paginate (1000 cap) until a short page. Cap at 20 pages (20k rows) for safety.
offset=0
echo '{"records":[' > "$COMBINED"
first=1
for _ in $(seq 1 20); do
  page=$(curl -sS -m 60 "https://api.data.gov.in/resource/${RESOURCE}?api-key=${KEY}&format=json&limit=1000&offset=${offset}")
  n=$(printf '%s' "$page" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('records',[])))")
  if [ "$n" -eq 0 ]; then break; fi
  rows=$(printf '%s' "$page" | python3 -c "import sys,json; print(','.join(json.dumps(r,ensure_ascii=False) for r in json.load(sys.stdin)['records']))")
  if [ "$first" -eq 1 ]; then first=0; else echo ',' >> "$COMBINED"; fi
  printf '%s' "$rows" >> "$COMBINED"
  offset=$((offset + n))
  if [ "$n" -lt 1000 ]; then break; fi
done
echo ']}' >> "$COMBINED"

# Coverage probe: count Delhi rows in the snapshot INDEPENDENTLY of alias resolution.
# This is the real R5 signal — "did Delhi appear today, and how many rows?" — and does
# not depend on whether Agmarknet's commodity spellings are aliased yet.
PROBE="data/coverage_probe.csv"
if [ ! -f "$PROBE" ]; then echo "captured_at_utc,total_rows,delhi_rows,delhi_markets" > "$PROBE"; fi
python3 - "$COMBINED" "$PROBE" "$TS" <<'PY'
import sys, json
combined, probe, ts = sys.argv[1], sys.argv[2], sys.argv[3]
recs = json.load(open(combined)).get("records", [])
def is_delhi(r):
    s = (r.get("state") or "").lower(); d = (r.get("district") or "").lower()
    m = (r.get("market") or "").lower()
    return ("delhi" in s) or ("delhi" in d) or any(k in m for k in ("azadpur", "keshopur", "delhi"))
delhi = [r for r in recs if is_delhi(r)]
markets = sorted({r.get("market", "?") for r in delhi})
with open(probe, "a") as fh:
    fh.write(f'{ts},{len(recs)},{len(delhi)},"{";".join(markets)}"\n')
print(f"[probe] total={len(recs)} delhi_rows={len(delhi)} markets={markets}")
PY

# Ensure schema + registry exist (idempotent), then ingest with an ingest_run record.
uv run vervana db upgrade >/dev/null
uv run vervana registry seed >/dev/null
echo "[$(date)] captured $offset rows -> $COMBINED"
uv run vervana ingest agmarknet-file "$COMBINED"
