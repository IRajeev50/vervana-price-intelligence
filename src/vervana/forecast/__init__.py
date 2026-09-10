"""Forecasting: baselines first, then SARIMA, then gradient boosting — always compared,
with a kill criterion enforced in code and a public prospective log."""

from vervana.forecast.kill import KillDecision, evaluate_kill, load_decision
from vervana.forecast.runner import backtest_all, format_backtest, summarize_and_persist

__all__ = [
    "KillDecision",
    "backtest_all",
    "evaluate_kill",
    "format_backtest",
    "load_decision",
    "summarize_and_persist",
]
