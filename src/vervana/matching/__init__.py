"""Entity-resolution matching: normalisation + two approaches + evaluation."""

from vervana.matching.evaluate import evaluate, format_report, load_eval_rows
from vervana.matching.lexical import Candidate, LexicalMatcher
from vervana.matching.normalize import normalize
from vervana.matching.phonetic import PhoneticMatcher

__all__ = [
    "Candidate",
    "LexicalMatcher",
    "PhoneticMatcher",
    "evaluate",
    "format_report",
    "load_eval_rows",
    "normalize",
]
