"""Approach B — phonetic matching.

Both query and index entries are reduced to a phonetic key (metaphone, applied after
transliteration to roman). Candidates sharing the query's phonetic key are preferred,
with a rapidfuzz tiebreak; if nothing shares a key, we fall back to the best fuzzy
score so the matcher always returns something rankable. This catches sound-alike
spelling drift ("mirch" ↔ "mirchi") that pure lexical distance can under-score.
"""

from __future__ import annotations

import jellyfish
from rapidfuzz import fuzz

from vervana.matching.lexical import Candidate


def phonetic_key(text_norm: str) -> str:
    """Metaphone key over the whitespace-joined tokens of a normalised string."""
    tokens = text_norm.split()
    return " ".join(jellyfish.metaphone(tok) for tok in tokens) if tokens else ""


class PhoneticMatcher:
    name = "phonetic"

    def __init__(self, index: list[tuple[str, str]]):
        # Precompute phonetic keys for the index once.
        self._index = [(text, canonical, phonetic_key(text)) for text, canonical in index]

    def match(self, query_norm: str, top_k: int = 1) -> list[Candidate]:
        qkey = phonetic_key(query_norm)
        scored: list[Candidate] = []
        for text, canonical, key in self._index:
            fuzzy = fuzz.WRatio(query_norm, text)
            # Reward a phonetic-key match strongly, then break ties on fuzzy score.
            score = (100.0 if key and key == qkey else 0.0) + fuzzy / 100.0
            scored.append(Candidate(canonical, score))
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]

    def best(self, query_norm: str) -> Candidate | None:
        top = self.match(query_norm, top_k=1)
        return top[0] if top else None
