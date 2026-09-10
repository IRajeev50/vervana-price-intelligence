"""Agricultural intelligence (M9): upstream crop signals -> supply -> price -> impact.

Same non-negotiables as the rest of the platform:
  * provenance first - every input signal is labelled observed / simulated / missing,
    and a simulated or missing input caps the confidence of every conclusion above it;
  * fail closed - when the evidence is not there, the chain says "insufficient
    evidence", never a confident guess;
  * honest horizons - the platform never claims a forecast horizon the crop's biology
    and storage economics cannot support (crop duration + storage buffer).
"""

from vervana.intelligence.chain import ChainStep, Direction, build_chain
from vervana.intelligence.crops import CropProfile, forecast_horizon, load_profiles
from vervana.intelligence.report import build_report, format_report, save_record
from vervana.intelligence.signals import Signal, SignalStatus, merge_signals

__all__ = [
    "ChainStep",
    "CropProfile",
    "Direction",
    "Signal",
    "SignalStatus",
    "build_chain",
    "build_report",
    "forecast_horizon",
    "format_report",
    "load_profiles",
    "merge_signals",
    "save_record",
]
