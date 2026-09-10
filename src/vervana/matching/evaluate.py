"""Leave-one-out evaluation of the two matching approaches against a labelled set.

For each labelled alias, we hide it and ask: given every OTHER known alias, does the
matcher resolve this held-out form to the correct canonical? This mirrors production
entity resolution (a new incoming string matched against the registry's known aliases)
and is a fair test of generalisation rather than memorisation.

Accuracy is reported overall and broken down by `alias_source_type`, because the
interesting finding is *where* matching works: transliteration/spelling variants
resolve well; cross-language forms with no near neighbour do not. That breakdown is the
honest signal, not a single headline number.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from vervana.matching.lexical import LexicalMatcher
from vervana.matching.normalize import normalize
from vervana.matching.phonetic import PhoneticMatcher


@dataclass
class EvalRow:
    alias_text: str
    alias_language: str
    alias_source_type: str
    canonical_name: str


@dataclass
class ApproachResult:
    approach: str
    total: int = 0
    correct: int = 0
    by_source_type: dict[str, list[int]] = field(
        default_factory=lambda: defaultdict(lambda: [0, 0])
    )
    failures: list[tuple[str, str, str]] = field(default_factory=list)  # (alias, expected, got)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def load_eval_rows(path: Path) -> list[EvalRow]:
    rows: list[EvalRow] = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                EvalRow(
                    alias_text=r["alias_text"].strip(),
                    alias_language=r.get("alias_language", "").strip(),
                    alias_source_type=r.get("alias_source_type", "").strip(),
                    canonical_name=r["canonical_name"].strip(),
                )
            )
    return rows


_MATCHERS = {"lexical": LexicalMatcher, "phonetic": PhoneticMatcher}


def evaluate(rows: list[EvalRow]) -> dict[str, ApproachResult]:
    """Run leave-one-out for both approaches. Returns {approach_name: result}."""
    normed = [(normalize(r.alias_text), r) for r in rows]
    results = {name: ApproachResult(approach=name) for name in _MATCHERS}

    for name, matcher_cls in _MATCHERS.items():
        res = results[name]
        for i, (q_norm, row) in enumerate(normed):
            index = [(o_norm, o.canonical_name) for j, (o_norm, o) in enumerate(normed) if j != i]
            best = matcher_cls(index).best(q_norm)
            got = best.canonical if best else "(none)"
            ok = got == row.canonical_name
            res.total += 1
            res.correct += int(ok)
            bucket = res.by_source_type[row.alias_source_type]
            bucket[1] += 1
            bucket[0] += int(ok)
            if not ok:
                res.failures.append((row.alias_text, row.canonical_name, got))
    return results


def format_report(results: dict[str, ApproachResult]) -> str:
    lines: list[str] = []
    lines.append("Matcher evaluation (leave-one-out)")
    lines.append("=" * 42)
    for name, res in results.items():
        lines.append(f"\nApproach: {name}")
        lines.append(f"  accuracy@1: {res.accuracy:.1%}  ({res.correct}/{res.total})")
        lines.append("  by source type:")
        for stype, (ok, tot) in sorted(res.by_source_type.items()):
            acc = ok / tot if tot else 0.0
            lines.append(f"    {stype or '(unlabelled)':<26} {acc:5.1%}  ({ok}/{tot})")
    return "\n".join(lines)
