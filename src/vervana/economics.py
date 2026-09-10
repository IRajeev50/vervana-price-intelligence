"""Platform economics — the observer-cost model (R12).

Emitted wherever a mandi is added, so the linear opex of human observers is never out of
sight. This is the cost story the ₹25k software ceiling does NOT cover.
"""

from __future__ import annotations

from dataclasses import dataclass

# Defaults (editable): a field observer's monthly stipend and how many per mandi.
DEFAULT_OBSERVER_STIPEND_RUPEES = 8000
DEFAULT_OBSERVERS_PER_MANDI = 1
# Delhi-NCR serviceable market from the validation study (₹6.6 crore/yr).
NCR_SAM_RUPEES_PER_YEAR = 6_60_00_000


@dataclass
class ObserverCostEstimate:
    n_mandis: int
    observers_per_mandi: int
    stipend_rupees: int
    monthly_rupees: int
    annual_rupees: int
    annual_pct_of_ncr_sam: float

    def as_lines(self) -> str:
        return (
            f"R12 observer-cost estimate: {self.n_mandis} mandi(s) × "
            f"{self.observers_per_mandi} observer(s) × ₹{self.stipend_rupees:,}/mo = "
            f"₹{self.monthly_rupees:,}/mo (₹{self.annual_rupees:,}/yr, "
            f"{self.annual_pct_of_ncr_sam:.1%} of the ₹6.6cr NCR SAM). "
            f"Payroll scales linearly with mandi count — this is opex, not software, and "
            f"is the binding constraint on unit economics."
        )


def estimate_observer_cost(
    n_mandis: int,
    *,
    observers_per_mandi: int = DEFAULT_OBSERVERS_PER_MANDI,
    stipend_rupees: int = DEFAULT_OBSERVER_STIPEND_RUPEES,
) -> ObserverCostEstimate:
    # RISK[R12-RECORDER-ECONOMICS]: The platform is assumed to scale like software, but
    # observer payroll scales LINEARLY with mandi count against a ₹6.6cr NCR SAM. This
    # estimate is emitted wherever a mandi is added so that linear opex can never be
    # forgotten behind the flat software cost. If annual observer cost approaches a large
    # fraction of the SAM, adding mandis destroys the unit economics — a config knob, not
    # a code change, but an expensive one.
    # Evidence: docs/RISK_REGISTER.md#r12-recorder-economics; RUNNING_COSTS.md §3
    # Verdict: PENDING
    monthly = n_mandis * observers_per_mandi * stipend_rupees
    annual = monthly * 12
    return ObserverCostEstimate(
        n_mandis=n_mandis,
        observers_per_mandi=observers_per_mandi,
        stipend_rupees=stipend_rupees,
        monthly_rupees=monthly,
        annual_rupees=annual,
        annual_pct_of_ncr_sam=annual / NCR_SAM_RUPEES_PER_YEAR,
    )
