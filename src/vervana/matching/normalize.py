"""Text normalisation for entity resolution.

Handles Devanagari + Hinglish: Devanagari is transliterated to a roman scheme so a
Hindi form and its Hinglish spelling collapse toward the same ascii string, which is
what makes lexical and phonetic matching work across scripts.

Note (an honest limitation, surfaced by the M1 evaluation): normalisation makes
*spelling variants of the same word* comparable ("शिमला मिर्च" ↔ "shimla mirch"). It
does NOT translate ("आलू" and "potato" are different words and stay different). Cross-
language resolution therefore depends on the registry already knowing a near form —
it is alias matching, not translation.
"""

from __future__ import annotations

import re
import unicodedata

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_WS = re.compile(r"\s+")


def has_devanagari(text: str) -> bool:
    return any(0x0900 <= ord(ch) <= 0x097F for ch in text)


def normalize(text: str) -> str:
    """Return a lowercased, transliterated, punctuation-stripped ascii-ish form."""
    t = unicodedata.normalize("NFC", text).strip()
    if has_devanagari(t):
        # ITRANS gives a readable roman form; lowercased afterwards for stability.
        t = transliterate(t, sanscript.DEVANAGARI, sanscript.ITRANS)
    t = t.lower()
    t = _NON_ALNUM.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    return t
