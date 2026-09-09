#!/usr/bin/env python3
"""Generate docs/RISK_REGISTER.md from (1) the seed definitions and (2) live code tags.

Two synchronized sections are emitted so drift is visible at a glance (the shape
the founder approved):

  * Seed definitions  — from scripts/risks_seed.yaml (what each risk means).
  * Live code tags     — from grepping the codebase for `RISK[<ID>]:` blocks
                         (file, line, one-line summary, and the Verdict: value).

The register is NEVER hand-edited. Run `make risks` (or this script) at the end of
every milestone; the output must be deterministic so committing it and re-running
produces no diff.

Tag format expected in code (Part 2):

    # RISK[R3-VIDEO-PROVENANCE]: one-line assumption summary...
    # ...more comment lines...
    # Evidence: <reference>
    # Verdict: PENDING | <a stated verdict>

The Verdict is read from the first `Verdict:` comment line within the 20 lines
following the tag.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = REPO_ROOT / "scripts" / "risks_seed.yaml"
OUTPUT_PATH = REPO_ROOT / "docs" / "RISK_REGISTER.md"

# Where to look for code tags. RISK tags mark load-bearing assumptions in the
# *application* — so we scan `src` and `scripts`, not `tests` (test fixtures
# legitimately contain tag-shaped string literals) and not `docs` (the spec text
# itself must not be mistaken for a live code tag).
SCAN_DIRS = ["src", "scripts"]
SCAN_SUFFIXES = {".py", ".sql", ".html", ".jinja", ".j2"}

# This generator documents the `RISK[...]:` format in its own docstring, so it must
# not scan itself — otherwise the example line is counted as a real tag. Any other
# file that only *describes* the format belongs here too.
EXCLUDE_FILES = {"scripts/gen_risk_register.py"}

TAG_RE = re.compile(r"RISK\[([A-Z0-9][A-Z0-9\-]*)\]\s*:\s*(.*)")
VERDICT_RE = re.compile(r"Verdict\s*:\s*(.+)", re.IGNORECASE)


@dataclass
class CodeTag:
    risk_id: str
    file: str
    line: int
    summary: str
    verdict: str


@dataclass
class RiskRow:
    risk_id: str
    assumption: str
    evidence: str
    note: str = ""
    tags: list[CodeTag] = field(default_factory=list)


def load_seed() -> dict[str, RiskRow]:
    data = yaml.safe_load(SEED_PATH.read_text(encoding="utf-8"))
    rows: dict[str, RiskRow] = {}
    for item in data["risks"]:
        rid = item["id"]
        rows[rid] = RiskRow(
            risk_id=rid,
            assumption=item.get("assumption", "").strip(),
            evidence=" ".join(item.get("evidence", "").split()),
            note=" ".join(item.get("note", "").split()),
        )
    return rows


def scan_code_tags() -> list[CodeTag]:
    tags: list[CodeTag] = []
    for d in SCAN_DIRS:
        base = REPO_ROOT / d
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in SCAN_SUFFIXES or not path.is_file():
                continue
            if str(path.relative_to(REPO_ROOT)) in EXCLUDE_FILES:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines):
                m = TAG_RE.search(line)
                if not m:
                    continue
                verdict = "(no Verdict: line found)"
                for follow in lines[i + 1 : i + 21]:
                    vm = VERDICT_RE.search(follow)
                    if vm:
                        verdict = vm.group(1).strip()
                        break
                tags.append(
                    CodeTag(
                        risk_id=m.group(1),
                        file=str(path.relative_to(REPO_ROOT)),
                        line=i + 1,
                        summary=m.group(2).strip(),
                        verdict=verdict,
                    )
                )
    return tags


def render(rows: dict[str, RiskRow], tags: list[CodeTag]) -> tuple[str, list[str]]:
    """Return (markdown, warnings)."""
    warnings: list[str] = []
    for t in tags:
        if t.risk_id in rows:
            rows[t.risk_id].tags.append(t)
        else:
            warnings.append(
                f"code tag RISK[{t.risk_id}] at {t.file}:{t.line} "
                "is not declared in risks_seed.yaml"
            )

    total_tags = len(tags)
    tagged_ids = sorted({t.risk_id for t in tags})
    untagged_ids = sorted(rid for rid, r in rows.items() if not r.tags)

    out: list[str] = []
    out.append("# RISK REGISTER")
    out.append("")
    out.append(
        "> **Generated file — do not hand-edit.** Produced by "
        "`scripts/gen_risk_register.py` (run via `make risks`) from "
        "`scripts/risks_seed.yaml` (definitions) and a grep of the codebase for "
        "`RISK[<ID>]:` tags (live occurrences). Edit the seed or the code, then "
        "regenerate."
    )
    out.append("")
    out.append(
        f"**Summary:** {len(rows)} risks declared · {len(tagged_ids)} have live code "
        f"tags · {len(untagged_ids)} not yet reached in code · {total_tags} tag "
        f"occurrences total."
    )
    out.append("")

    if warnings:
        out.append("## ⚠️ Drift warnings")
        out.append("")
        for w in warnings:
            out.append(f"- {w}")
        out.append("")

    # Section 1: seed definitions + tag status
    out.append("## 1. Declared risks (definitions)")
    out.append("")
    out.append("| ID | Assumption | Code tags | Verdict(s) |")
    out.append("|---|---|---|---|")
    for rid in rows:  # dict preserves seed order
        r = rows[rid]
        if r.tags:
            verdicts = sorted({t.verdict for t in r.tags})
            tag_count = f"{len(r.tags)}"
        else:
            verdicts = ["— not yet reached in code —"]
            tag_count = "0"
        out.append(f"| `{rid}` | {r.assumption} | {tag_count} | {'; '.join(verdicts)} |")
    out.append("")

    # Section 2: live code tags
    out.append("## 2. Live code tags (grepped from source)")
    out.append("")
    if tags:
        out.append("| ID | Location | Summary | Verdict |")
        out.append("|---|---|---|---|")
        for t in sorted(tags, key=lambda x: (x.risk_id, x.file, x.line)):
            summary = t.summary if len(t.summary) <= 90 else t.summary[:87] + "..."
            out.append(f"| `{t.risk_id}` | `{t.file}:{t.line}` | {summary} | {t.verdict} |")
    else:
        out.append(
            "_No `RISK[...]` tags in code yet._ Expected at M0 (foundations only). "
            "Tags appear as the data model and connectors are built (M1+)."
        )
    out.append("")

    # Section 3: evidence detail
    out.append("## 3. Evidence against each assumption")
    out.append("")
    for rid in rows:
        r = rows[rid]
        out.append(f"### `{rid}`")
        out.append("")
        out.append(f"- **Assumption:** {r.assumption}")
        out.append(f"- **Evidence against it:** {r.evidence}")
        if r.note:
            out.append(f"- **Note:** {r.note}")
        out.append("")

    return "\n".join(out) + "\n", warnings


def main() -> int:
    rows = load_seed()
    tags = scan_code_tags()
    markdown, warnings = render(rows, tags)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}: {len(rows)} risks, {len(tags)} code tags.")
    for w in warnings:
        print(f"  WARNING: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
