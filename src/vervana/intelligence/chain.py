"""The reasoning chain (M9): signals -> production -> supply -> balance -> price
pressure -> second-order impacts. Every arrow is an explicit rule with named
inputs; every node reports provenance and confidence.

These are HEURISTIC RULES, not learned models. They encode the agronomic logic
(deficit rain + falling NDVI + low reservoirs -> production down) so the platform
can reason transparently while it has too little data to learn. Thresholds are
deliberate, documented here, and easy to challenge.

Confidence rule (fail closed):
  * a step built only on observed signals can reach HIGH confidence;
  * any simulated input caps the step at LOW (<= 0.35) and marks the whole
    report as a development exercise;
  * a step with no inputs is UNKNOWN - the chain says "insufficient evidence"
    instead of guessing.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from vervana.intelligence.signals import STEP_SIGNALS, Signal, SignalStatus

OBSERVED_CONF = 0.8
SIMULATED_CONF = 0.35
# Direction scoring thresholds (heuristic, documented):
RAIN_DEFICIT_SEVERE = -15.0  # % below LPA
RESERVOIR_LOW = 55.0  # % of capacity
NDVI_BAD = -0.05
ACREAGE_DOWN = -3.0  # %
ARRIVALS_DOWN = -10.0  # %
SOWING_BEHIND = 70.0  # % of normal area sown by this date -> area likely down
SOWING_AHEAD = 95.0  # % -> sowing effectively complete/on time
HARVEST_UNDERWAY = 50.0  # % of area harvested -> supply is reaching mandis now
STOCKS_TIGHT_VS_CONSUMPTION = 0.15  # stocks < 15% of annual consumption


class Direction(enum.StrEnum):
    up = "up"
    down = "down"
    neutral = "neutral"
    unknown = "unknown"


@dataclass
class ChainStep:
    name: str
    finding: str
    direction: Direction
    confidence: float
    inputs: list[Signal] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.direction == Direction.unknown:
            return "insufficient evidence"
        statuses = {s.status for s in self.inputs}
        if SignalStatus.simulated in statuses:
            return "simulated"
        if statuses == {SignalStatus.observed}:
            return "observed"
        return "derived"


def _by_kind(signals: list[Signal]) -> dict[str, list[Signal]]:
    out: dict[str, list[Signal]] = {}
    for s in signals:
        if s.status != SignalStatus.missing:
            out.setdefault(s.kind, []).append(s)
    return out


def _num(sigs: list[Signal]) -> float | None:
    vals = [s.value_numeric for s in sigs if s.value_numeric is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)  # mean of same-kind regional values


def _step_confidence(inputs: list[Signal]) -> float:
    if not inputs:
        return 0.0
    if any(s.status == SignalStatus.simulated for s in inputs):
        return SIMULATED_CONF
    return OBSERVED_CONF


def build_chain(signals: list[Signal]) -> list[ChainStep]:
    """Build the five-step chain from merged (observed + simulated + missing) signals."""
    have = _by_kind(signals)
    steps: list[ChainStep] = []

    # 1. Production outlook ---------------------------------------------------
    prod_inputs = [s for k in STEP_SIGNALS["production"] for s in have.get(k, [])]
    prod_missing = [k for k in STEP_SIGNALS["production"] if k not in have]
    if not prod_inputs:
        steps.append(
            ChainStep(
                "production",
                "No production signals connected.",
                Direction.unknown,
                0.0,
                [],
                prod_missing,
            )
        )
    else:
        score = 0
        parts = []
        rain = _num(have.get("rainfall_deficit_pct", []))
        if rain is not None:
            score += -1 if rain <= RAIN_DEFICIT_SEVERE else (0 if rain < 0 else 1)
            parts.append(f"rainfall {rain:g}% vs normal")
        ndvi = _num(have.get("ndvi_anomaly", []))
        if ndvi is not None:
            score += -1 if ndvi <= NDVI_BAD else (0 if ndvi < 0 else 1)
            parts.append(f"NDVI anomaly {ndvi:g}")
        res = _num(have.get("reservoir_pct", []))
        if res is not None:
            score += -1 if res <= RESERVOIR_LOW else 1
            parts.append(f"reservoirs at {res:g}% of capacity")
        acr = _num(have.get("acreage_change_pct", []))
        if acr is not None:
            score += -1 if acr <= ACREAGE_DOWN else (0 if acr < 0 else 1)
            parts.append(f"acreage {acr:g}% vs last year")
        sowing = _num(have.get("sowing_progress_pct", []))
        if sowing is not None:
            # Event-detected sowing progress is the earliest acreage signal:
            # behind normal at this date means area is likely to end down.
            score += -1 if sowing < SOWING_BEHIND else (1 if sowing > SOWING_AHEAD else 0)
            parts.append(f"sowing progress {sowing:g}% of normal")
        direction = (
            Direction.down if score <= -2 else (Direction.up if score >= 2 else Direction.neutral)
        )
        finding = {
            Direction.down: "Production outlook DOWN: " + "; ".join(parts) + ".",
            Direction.up: "Production outlook UP: " + "; ".join(parts) + ".",
            Direction.neutral: "Production outlook MIXED: " + "; ".join(parts) + ".",
        }[direction]
        steps.append(
            ChainStep(
                "production",
                finding,
                direction,
                _step_confidence(prod_inputs),
                prod_inputs,
                prod_missing,
            )
        )

    # 2. Supply outlook ---------------------------------------------------------
    sup_inputs = [s for k in STEP_SIGNALS["supply"] for s in have.get(k, [])]
    sup_missing = [k for k in STEP_SIGNALS["supply"] if k not in have]
    prod_dir = steps[-1].direction
    if not sup_inputs and prod_dir == Direction.unknown:
        steps.append(
            ChainStep(
                "supply", "No supply signals connected.", Direction.unknown, 0.0, [], sup_missing
            )
        )
    else:
        score = 0
        parts = []
        arr = _num(have.get("arrivals_change_pct", []))
        if arr is not None:
            score += -1 if arr <= ARRIVALS_DOWN else (0 if arr < 0 else 1)
            parts.append(f"mandi arrivals {arr:g}% vs normal")
        harvest = _num(have.get("harvest_progress_pct", []))
        if harvest is not None:
            # Harvest progress is a TIMING signal, not a volume signal: past the
            # halfway mark, the crop is physically moving toward the mandis now.
            score += 1 if harvest >= HARVEST_UNDERWAY else 0
            parts.append(f"harvest progress {harvest:g}% of area")
        stocks = _num(have.get("stocks_lmt", []))
        cons = _num(have.get("consumption_lmt", []))
        if stocks is not None and cons:
            tight = stocks < STOCKS_TIGHT_VS_CONSUMPTION * cons
            score += -1 if tight else 1
            level = "tight" if tight else "comfortable"
            parts.append(f"stocks {stocks:g} LMT vs consumption {cons:g} LMT ({level})")
        if prod_dir == Direction.down:
            score -= 1
            parts.append("production outlook is down")
        elif prod_dir == Direction.up:
            score += 1
            parts.append("production outlook is up")
        direction = (
            Direction.down if score <= -1 else (Direction.up if score >= 1 else Direction.neutral)
        )
        finding = (
            f"Supply outlook {direction.value.upper()}: " + "; ".join(parts) + "."
            if parts
            else "Supply outlook unclear."
        )
        steps.append(
            ChainStep(
                "supply",
                finding,
                direction,
                _step_confidence(sup_inputs or prod_inputs),
                sup_inputs,
                sup_missing,
            )
        )

    # 3. Balance sheet ------------------------------------------------------------
    bal_inputs = [s for k in STEP_SIGNALS["balance"] for s in have.get(k, [])]
    bal_missing = [k for k in STEP_SIGNALS["balance"] if k not in have]
    production = _num(have.get("production_lmt", []))
    consumption = _num(have.get("consumption_lmt", []))
    if production is None or consumption is None:
        steps.append(
            ChainStep(
                "balance",
                "No production/consumption balance sheet connected.",
                Direction.unknown,
                0.0,
                bal_inputs,
                bal_missing,
            )
        )
    else:
        gap = production - consumption
        direction = Direction.down if gap < 0 else (Direction.up if gap > 0 else Direction.neutral)
        word = "DEFICIT" if gap < 0 else ("SURPLUS" if gap > 0 else "BALANCED")
        steps.append(
            ChainStep(
                "balance",
                f"Balance sheet {word}: production {production:g} vs consumption "
                f"{consumption:g} LMT (gap {gap:+g} LMT).",
                direction,
                _step_confidence(bal_inputs),
                bal_inputs,
                bal_missing,
            )
        )

    # 4. Price pressure -----------------------------------------------------------
    sup_dir = steps[1].direction
    bal_dir = steps[2].direction
    votes = [d for d in (sup_dir, bal_dir) if d != Direction.unknown]
    if not votes:
        steps.append(
            ChainStep(
                "price_pressure",
                "Cannot assess price pressure without supply or balance evidence.",
                Direction.unknown,
                0.0,
                [],
                [],
            )
        )
    else:
        pressure_up = sum(1 for d in votes if d == Direction.down)  # tight supply => price up
        pressure_down = sum(1 for d in votes if d == Direction.up)
        if pressure_up > pressure_down:
            direction = Direction.up
            finding = "Price pressure UP: supply is tight relative to demand."
        elif pressure_down > pressure_up:
            direction = Direction.down
            finding = "Price pressure DOWN: supply is comfortable relative to demand."
        else:
            direction = Direction.neutral
            finding = "Price pressure MIXED: supply and balance signals disagree."
        conf = (
            min(steps[1].confidence, steps[2].confidence)
            if steps[2].direction != Direction.unknown
            else steps[1].confidence
        )
        steps.append(
            ChainStep(
                "price_pressure",
                finding,
                direction,
                conf,
                steps[1].inputs + steps[2].inputs,
                [],
            )
        )

    # 5. Second-order impacts -------------------------------------------------------
    imp_inputs = [s for k in STEP_SIGNALS["impacts"] for s in have.get(k, [])]
    imp_missing = [k for k in STEP_SIGNALS["impacts"] if k not in have]
    price_dir = steps[3].direction
    policy = [s for s in imp_inputs if s.kind == "policy_event"]
    policy_idx = min(3, len(policy))  # 0-3: count of active interventions observed
    if price_dir == Direction.unknown:
        finding = "Second-order impacts cannot be assessed yet."
        direction = Direction.unknown
    else:
        parts = []
        if price_dir == Direction.up:
            parts.append("farmer realisations likely up (where farmers sell raw produce)")
            parts.append("procurement cost pressure for HoReCa/processors")
            parts.append("downstream food-inflation pressure")
        elif price_dir == Direction.down:
            parts.append("farmer realisations under pressure")
            parts.append("procurement relief for HoReCa/processors")
        input_sales = _num([s for s in imp_inputs if s.kind == "input_sales_change_pct"])
        if input_sales is not None:
            parts.append(f"agri-input sales {input_sales:+g}% vs normal")
        if policy:
            parts.append(
                f"policy-pressure index {policy_idx}/3 "
                f"({len(policy)} active intervention(s) observed)"
            )
        finding = "Impacts: " + "; ".join(parts) + "."
        direction = price_dir
    steps.append(
        ChainStep(
            "impacts",
            finding,
            direction,
            _step_confidence(imp_inputs) if imp_inputs else SIMULATED_CONF,
            imp_inputs,
            imp_missing,
        )
    )
    return steps


def report_verdict(steps: list[ChainStep]) -> tuple[str, str]:
    """The honesty verdict for a chain. Strong claims need observed evidence all the
    way through; simulated inputs demote the report to a development watchlist."""
    price_step = next((s for s in steps if s.name == "price_pressure"), None)  #
    if price_step is None or price_step.direction == Direction.unknown:
        return (
            "no signal",
            "Core evidence is missing. The platform does not issue an outlook without it.",
        )
    statuses = {s.status for s in steps}
    if "simulated" in statuses:
        return (
            "watchlist (simulated inputs)",
            "This chain runs on bundled simulated inputs for development. Direction is "
            "plausible but NOT a live finding - connect observed feeds before acting on it.",
        )
    if "insufficient evidence" in statuses:
        return (
            "watchlist (partial evidence)",
            "Some chain steps lack evidence; the outlook is provisional.",
        )
    return (
        "signal (observed)",
        "All chain steps rest on observed, sourced inputs.",
    )
