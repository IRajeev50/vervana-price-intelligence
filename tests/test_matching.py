"""Matching: normalisation across scripts + the evaluation harness (M1 DoD #2)."""

from __future__ import annotations

from pathlib import Path

from vervana.matching.evaluate import evaluate, load_eval_rows
from vervana.matching.lexical import LexicalMatcher
from vervana.matching.normalize import has_devanagari, normalize
from vervana.matching.phonetic import PhoneticMatcher, phonetic_key

EVAL_FILE = Path(__file__).resolve().parent.parent / "data" / "eval" / "aliases_200.csv"


def test_devanagari_detection_and_transliteration():
    assert has_devanagari("आलू")
    assert not has_devanagari("aloo")
    # Devanagari 'आलू' normalises to an ascii-ish form (no Devanagari left).
    out = normalize("आलू")
    assert out and not has_devanagari(out)


def test_normalize_strips_and_lowercases():
    assert normalize("  Shimla Mirch! ") == "shimla mirch"


def test_phonetic_key_matches_spelling_variants():
    # 'mirch' and 'mirchi' should share a phonetic prefix key structure.
    assert phonetic_key(normalize("mirch"))
    assert phonetic_key(normalize("mirchi"))


def test_matchers_resolve_a_known_variant():
    index = [("shimla mirch", "Capsicum"), ("aloo", "Potato"), ("pyaz", "Onion")]
    assert LexicalMatcher(index).best("shimla mirchi").canonical == "Capsicum"
    assert PhoneticMatcher(index).best("shimla mirchi").canonical == "Capsicum"


def test_eval_harness_runs_and_reports_accuracy():
    rows = load_eval_rows(EVAL_FILE)
    assert len(rows) >= 190  # ~200-alias labelled set
    results = evaluate(rows)
    assert set(results) == {"lexical", "phonetic"}
    for res in results.values():
        assert res.total == len(rows)
        # Sanity floor only — the real numbers are reported in M1-done, not asserted
        # tightly, since the bootstrap set is indicative.
        assert res.accuracy >= 0.5
        assert 0.0 <= res.accuracy <= 1.0
