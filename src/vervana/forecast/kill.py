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


# --- band kill discipline (M14) -----------------------------------------------------
# A band ships for a (commodity, mandi) series only if its p50 beats BOTH the anchor
# (naive) and seasonal_naive on MAE and WAPE, AND realized coverage lands in the
# acceptance window. Decision 3a: the band is p10/p50/p90 (80% nominal), so coverage is
# judged against [0.75, 0.88], centered on the nominal 80%.
BAND_COV_LO = 0.75
BAND_COV_HI = 0.88
BAND_RESULTS_PATH = REPO_ROOT / "data" / "backtests" / "band_latest.json"


@dataclass
class BandKillDecision:
    shippable: bool
    reason: str


def evaluate_band_kill(
    *,
    band_mae: float,
    band_wape: float,
    coverage: float,
    anchor_mae: float,
    anchor_wape: float,
    seasonal_mae: float,
    seasonal_wape: float,
) -> BandKillDecision:
    """Pure ship/no-ship for one series. Fails on the first unmet condition."""
    beats_mae = band_mae < anchor_mae and band_mae < seasonal_mae
    beats_wape = band_wape < anchor_wape and band_wape < seasonal_wape
    covered = BAND_COV_LO <= coverage <= BAND_COV_HI
    if beats_mae and beats_wape and covered:
        return BandKillDecision(
            True,
            f"band p50 beats anchor+seasonal on MAE and WAPE; coverage {coverage:.0%} "
            f"within [{BAND_COV_LO:.0%},{BAND_COV_HI:.0%}] — may serve.",
        )
    why = []
    if not beats_mae:
        why.append(f"MAE {band_mae / 100:.2f} not below anchor/seasonal")
    if not beats_wape:
        why.append(f"WAPE {band_wape:.1%} not below anchor/seasonal")
    if not covered:
        why.append(f"coverage {coverage:.0%} outside [{BAND_COV_LO:.0%},{BAND_COV_HI:.0%}]")
    return BandKillDecision(False, "band falls back to labelled baseline band: " + "; ".join(why))


def decide_commodity(mandi_pass: list[bool]) -> bool:
    """Per-commodity roll-up: ship iff a MAJORITY of that commodity's qualifying mandis
    pass. No qualifying mandis -> not shippable (fail closed)."""
    if not mandi_pass:
        return False
    return sum(mandi_pass) * 2 > len(mandi_pass)


def save_band_results(results: dict) -> Path:
    BAND_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    BAND_RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return BAND_RESULTS_PATH


def load_band_decision(commodity: str) -> BandKillDecision:
    """Runtime gate for one commodity's band, fail-closed from band_latest.json."""
    if not BAND_RESULTS_PATH.exists():
        return BandKillDecision(False, "no band backtest on record — serving baseline band.")
    data = json.loads(BAND_RESULTS_PATH.read_text(encoding="utf-8"))
    per = data.get("per_commodity", {})
    entry = per.get(commodity)
    if not entry:
        return BandKillDecision(False, f"no band verdict for {commodity} — baseline band.")
    shippable = bool(entry.get("shippable"))
    return BandKillDecision(shippable, entry.get("reason", ""))
