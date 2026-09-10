"""Approach A — lexical + transliteration matching.

Index of (normalised alias text -> canonical label). A query is normalised the same
way and scored against every index entry with rapidfuzz WRatio; the best-scoring
canonical wins. Cheap, deterministic, no heavy dependencies (fits the ₹25k box).
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz


@dataclass
class Candidate:
    canonical: str
    score: float


class LexicalMatcher:
    """rapidfuzz over normalised alias strings.

    Takes an index of already-normalised (text, canonical) pairs so the caller
    controls normalisation (and can cache it across a leave-one-out evaluation).
    """

    name = "lexical"

    def __init__(self, index: list[tuple[str, str]]):
        self._index = index

    def match(self, query_norm: str, top_k: int = 1) -> list[Candidate]:
        scored = [
            Candidate(canonical, fuzz.WRatio(query_norm, text)) for text, canonical in self._index
        ]
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]

    def best(self, query_norm: str) -> Candidate | None:
        top = self.match(query_norm, top_k=1)
        return top[0] if top else None
