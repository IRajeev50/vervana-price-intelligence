# M6 — Transcript / video-quote ingest · DONE (manual-file path)

- **Status:** COMPLETE via the **human-curated manual-file path**. The founder supplied a
  92-day corpus (a person watched the videos and transcribed price statements), so this is
  a manual import — NOT a scraper and NOT a raw-transcript parser — which stays within the
  letter of Gate 1. **Gate 1's legal opinion on commercial use is still unconfirmed**, so
  the connector is droppable and the raw corpus is kept out of git (R8).
- **Date:** 2026-09-10. **84 offline tests pass, lint clean.**

## Source
`Mandi Price Data - 9 Jun to 9 Sep 2026.numbers` → `data/raw/transcript/corpus.csv`
(git-ignored). **6,335 rows, 2026-06-09 → 2026-09-09**, two Delhi mandis:
**Azadpur (4,249)** and **Keshopur (2,086)** — the exact markets Agmarknet does not carry.

## Definition of done vs actual
| Criterion (Part 4.2 / M6) | Result |
|---|---|
| Pluggable connector, droppable | ✅ `TranscriptConnector`; `fetch_raw` refuses (no YouTube fetch); disableable via config. |
| Parser: date/commodity/variety/range/unit/arrivals/carryover/commentary/raw quote | ✅ all columns mapped; provenance = Source Video URL + raw transcript quote. |
| Digit-merge detection (e.g. 4546→45–46), flag never correct | ✅ caught real cases: `2023→20-23`, `1415→14-15`, `1920→19-20` — flagged, never corrected. |
| Range-sanity flagging | ✅ added after the data exposed a gap (`₹800–112000` slipped through low≤high) — now flags implausible highs / >10× ranges. |
| Review-queue / flags surfaced | ✅ every accepted row stores `detected_flags` in its provenance JSON. |
| Corpus parsed with reported flag rate; show 20 rows incl. 3 failures | ✅ below. |

## Real output (`scripts/m6_report.py`)
```
ingest_run: in=6335 accepted=2570 rejected=3765
  rejected [1310] unresolved_commodity: Vegetables (all)   # aggregates, not one commodity
  rejected [534]  unresolved_commodity: Gold & Silver      # some vlogs cover bullion
  rejected [508]  unresolved_commodity: Fruits (all) + Vegetables (all)  # composites
  rejected [73]   no_price_extracted

accepted video-quote rows: 2570 · carrying a flag: 7.2% · digit-merge suspected: 33
canonical ₹/kg: 0  (unit ALWAYS unstated in video → NULL, never guessed)

3 digit-merge FLAGGED rows (flagged, never corrected):
  #6693 Mango @ Azadpur ₹2023-2023  | digit_merge_suspected: 2023->20-23
        quote: "...दशहरी असल में बिक रही है 2023 30 इसकी वजह..."
  #6843 Potato @ Azadpur ₹1415-1415 | digit_merge_suspected: 1415->14-15
  #7161 Tomato @ Keshopur ₹1920-1920 | digit_merge_suspected: 1920->19-20
```
Failures explained: aggregate "commodities" (Vegetables (all), Gold & Silver, composites)
correctly don't resolve to one commodity; 73 rows had no extractable price.

## Then — the FIRST real forecast backtest (M4 on real Delhi data)
With ~90 days of Delhi quotes, `forecast backtest` ran on real series (video quotes are
`quote_indicative`; the series uses range midpoints, **R13**):
```
Onion  @ Azadpur (76d): GB dir 63.6% vs seasonal 65.5% → NOT shippable (R7)
Potato @ Azadpur (72d): GB dir 60.8% vs seasonal 70.6% → NOT shippable (R7)
Tomato @ Azadpur (50d): GB dir 58.6% vs seasonal 51.7% → SHIPPABLE (clears +10%)
```
The kill criterion fires **per commodity** — most fail (R7 vindicated), Tomato passes.
**Caveat, stated plainly:** the video unit is unstated and inconsistent, so absolute MAE
(the "₹/kg" column) is in a mixed quote unit and is NOT reliable ₹/kg; sMAPE >100% signals
noisy/artefact-laden series. **Directional accuracy** is the trustworthy metric here, and
even it clears the bar only sometimes. This is real forecasting evidence, and it is weak —
exactly what R7 predicts.

## Risk tags (register now shows all 13, 12 in code + R1)
Added `R3-VIDEO-PROVENANCE` and `R8-YOUTUBE-TOS` (transcript.py), and `R1` in the digest.

## Honest status
This unblocks Delhi history — a real gain. But it is **video-quote data, not executed
prices** (R3): until we compare it to trader invoices (M5), it is a sentiment/quote signal,
never treated as an executed price (the guard enforces this). And Gate 1 is unresolved —
if the legal opinion is negative, this connector is dropped and the corpus deleted.

## Cost impact
₹0 fixed (a `numbers-parser` dev import for the one-off export). No YouTube API, no ASR.
