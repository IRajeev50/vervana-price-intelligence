# Running Vervana on your Mac — step by step

Copy-paste each block. All commands run from the project folder.

```bash
cd "/Users/rajeevsingh.1/Mandi bhav"
```

If a command ever says `uv: command not found`, run this once in that terminal
(uv lives in `~/.local/bin`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## A. Fastest path — the platform is already set up

Your database (`vervana.dev.sqlite3`) already holds the data. Just start the app:

```bash
uv run vervana serve
```

Then open **http://127.0.0.1:8000** in a browser. Press `Ctrl+C` in the terminal to stop it.

> Not sure if it's ready? Run `uv run vervana doctor` — it prints a checklist of
> what's done, what's missing, and the exact next command.

---

## B. Fresh start (new clone, or empty database)

**1. Install dependencies** (also downloads the right Python 3.12):

```bash
uv sync
```

**2. Create the database + load the commodity/market registry** (safe to re-run):

```bash
uv run vervana setup
```

**3. Add your data.gov.in API key** — needed only for live prices. Open `.env` and
paste your key after `VERVANA_DATA_GOV_IN_API_KEY=` (create `.env` from the example
first if it doesn't exist):

```bash
cp -n .env.example .env && open -e .env
```

**4. Pull today's live prices:**

```bash
uv run vervana ingest agmarknet --state Delhi --max-records 1000
uv run vervana ingest history      # shows every run, including failures
```

data.gov.in is often slow; if a capture times out, just run it again (re-ingesting
the same rows is safe — duplicates are rejected, not doubled).

**5. Start the app:**

```bash
uv run vervana serve
```

Open **http://127.0.0.1:8000**.

---

## C. Optional extras (only if you want them)

```bash
# Load the full national snapshot (more markets than just Delhi):
bash scripts/daily_capture.sh
SNAP=$(ls -t data/raw/agmarknet/snapshot_*.json | head -1)
uv run vervana registry bootstrap "$SNAP"     # learn the snapshot's commodity/market names
uv run vervana ingest agmarknet-file "$SNAP"  # ingest the prices

# Import the video-quote corpus (Delhi), quick-commerce panel, and post a forecast:
uv run vervana ingest transcript-csv data/raw/transcript/corpus.csv
uv run vervana ingest qcomm-csv data/samples/qcomm_sample.csv
uv run vervana forecast backtest Onion --market Azadpur   # sets the kill decision
uv run vervana forecast prospective                        # posts tomorrow's call

# Save an intelligence outlook so it appears in the crop portfolio:
uv run vervana intelligence outlook Onion --save
```

---

## The pages, once it's running (http://127.0.0.1:8000)

Dashboard · Prices · Benchmark · HoReCa digest · Coverage (R5) · Forecast log ·
**Intelligence** · Outlook calendar · Review · Ingest.

## If something looks empty or wrong

```bash
uv run vervana doctor    # what's set up, what's missing, the exact next command
uv run vervana ingest history   # did the last capture succeed?
make test                # confirm the code itself is healthy
```
