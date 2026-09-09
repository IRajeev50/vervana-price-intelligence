"""The risk-register generator: parses seed, parses tags, is deterministic."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_PATH = REPO_ROOT / "scripts" / "gen_risk_register.py"

# Load the script as a module (it lives in scripts/, not the package). It must be
# registered in sys.modules before exec_module, or @dataclass under
# `from __future__ import annotations` fails to resolve its own module.
_spec = importlib.util.spec_from_file_location("gen_risk_register", GEN_PATH)
assert _spec and _spec.loader
gen = importlib.util.module_from_spec(_spec)
sys.modules["gen_risk_register"] = gen
_spec.loader.exec_module(gen)


def test_seed_loads_all_declared_risks() -> None:
    rows = gen.load_seed()
    # 12 spec risks + R13 candidate raised in UNDERSTANDING.md.
    assert len(rows) == 13
    assert "R5-COVERAGE-EDGE" in rows
    assert "R13-RANGE-MIDPOINT" in rows


def test_generator_does_not_tag_itself() -> None:
    # The generator's own docstring documents the RISK[...] format; it must be
    # excluded so its example is not counted as a live tag.
    tags = gen.scan_code_tags()
    assert all(t.file != "scripts/gen_risk_register.py" for t in tags)


def test_render_is_deterministic() -> None:
    rows = gen.load_seed()
    tags = gen.scan_code_tags()
    md1, _ = gen.render(gen.load_seed(), tags)
    md2, _ = gen.render(rows, tags)
    assert md1 == md2


def test_tag_parsing_and_verdict_extraction(tmp_path: Path, monkeypatch) -> None:
    # Write a fake source file with one real tag + verdict, point the scanner at it.
    src = tmp_path / "src"
    src.mkdir()
    (src / "sample.py").write_text(
        "# RISK[R5-COVERAGE-EDGE]: coverage assumed bad here\n"
        "# Evidence: docs/RISK_REGISTER.md\n"
        "# Verdict: PENDING\n"
        "x = 1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gen, "SCAN_DIRS", ["src"])
    tags = gen.scan_code_tags()
    assert len(tags) == 1
    assert tags[0].risk_id == "R5-COVERAGE-EDGE"
    assert tags[0].verdict == "PENDING"
    assert tags[0].line == 1


def test_unknown_tag_produces_drift_warning(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "sample.py").write_text(
        "# RISK[R99-UNDECLARED]: not in the seed\n# Verdict: PENDING\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gen, "SCAN_DIRS", ["src"])
    rows = gen.load_seed()
    _, warnings = gen.render(rows, gen.scan_code_tags())
    assert any("R99-UNDECLARED" in w for w in warnings)
