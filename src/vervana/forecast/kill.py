"""The forecast kill criterion, enforced in code (§5.3).

If gradient boosting does not beat seasonal-naive by more than 10% on directional
accuracy, the serving layer must expose baseline-plus-interval only, labelled as such.
This is a runtime check against stored backtest results — not a decision anyone has to
remember to make.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RESULTS_PATH = REPO_ROOT / "data" / "backtests" / "latest.json"
MARGIN = 0.10  # GB must beat seasonal-naive by >10% (relative) on directional accuracy


@dataclass
class KillDecision:
    model_shippable: bool
    reason: str
    gb_directional: float | None = None
    seasonal_directional: float | None = None


def evaluate_kill(gb_directional: float, seasonal_directional: float) -> KillDecision:
    """Pure decision: does GB clear seasonal-naive by the required margin?"""
    if seasonal_directional <= 0:
        threshold = gb_directional  # avoid divide-by-zero; any positive GB passes
        passes = gb_directional > 0
    else:
        threshold = seasonal_directional * (1 + MARGIN)
        passes = gb_directional > threshold
    if passes:
        reason = (
            f"gradient_boosting directional {gb_directional:.1%} beats seasonal_naive "
            f"{seasonal_directional:.1%} by >10% — model may serve."
        )
    else:
        reason = (
            f"gradient_boosting directional {gb_directional:.1%} does NOT beat "
            f"seasonal_naive {seasonal_directional:.1%} by >10% (needs >{threshold:.1%}) "
            f"— serving falls back to baseline + interval, labelled as such (R7)."
        )
    return KillDecision(passes, reason, gb_directional, seasonal_directional)


def save_results(results: dict) -> Path:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return RESULTS_PATH


def load_decision() -> KillDecision:
    """Read the stored backtest and decide, at runtime, whether the model may serve.

    Absent results ⇒ not shippable (fail closed): we never serve a model we haven't
    proven beats the baselines.
    """
    if not RESULTS_PATH.exists():
        return KillDecision(False, "no backtest results on record — serving baselines only.")
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    gb = data.get("gradient_boosting_directional")
    sn = data.get("seasonal_naive_directional")
    if gb is None or sn is None:
        return KillDecision(False, "backtest results incomplete — serving baselines only.")
    return evaluate_kill(gb, sn)
