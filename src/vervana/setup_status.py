"""First-run setup status: one checklist shared by the CLI and the dashboard.

Answers "why is my platform empty?" from live state, with the exact next command
for whatever is missing. The checklist keeps the two kinds of data visibly
separate (Part 7 honesty rules):

- **Reference data** (commodity/market registry) comes from the repo's seed
  files via ``vervana setup`` — it is not live data and never claims to be.
- **Live prices** arrive only through recorded ingest runs; the checklist never
  fabricates or implies observations that were not captured.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.config import Settings
from vervana.models.entities import Commodity, Market
from vervana.models.ingest import IngestRun
from vervana.models.observations import PriceObservation

# The one documented live-capture command, kept in a single place so the CLI,
# the dashboard, and the docs cannot drift apart.
FIRST_INGEST_COMMAND = "uv run vervana ingest agmarknet --state Delhi --max-records 100"
SETUP_COMMAND = "uv run vervana setup"
KEY_ENV_VAR = "VERVANA_DATA_GOV_IN_API_KEY"


@dataclass(frozen=True)
class SetupStep:
    """One first-run requirement and its live state."""

    key: str
    label: str
    ok: bool
    detail: str
    action: str | None  # exact next step when not ok; None when done


def collect_setup_steps(session: Session, settings: Settings) -> list[SetupStep]:
    """Inspect live state and return the ordered first-run checklist."""
    commodities = session.scalar(select(func.count()).select_from(Commodity)) or 0
    markets = session.scalar(select(func.count()).select_from(Market)) or 0
    observations = session.scalar(select(func.count()).select_from(PriceObservation)) or 0
    last_run = session.scalar(select(IngestRun).order_by(IngestRun.started_at.desc()))

    steps: list[SetupStep] = []

    registry_ok = commodities > 0 and markets > 0
    steps.append(
        SetupStep(
            key="registry",
            label="Reference data seeded (commodities and markets)",
            ok=registry_ok,
            detail=(
                f"{commodities} commodities, {markets} markets loaded from the repo seed files"
                if registry_ok
                else "registry is empty, so nothing can be matched or listed"
            ),
            action=None if registry_ok else SETUP_COMMAND,
        )
    )

    key_ok = bool(settings.data_gov_in_api_key)
    steps.append(
        SetupStep(
            key="api_key",
            label="data.gov.in API key configured",
            ok=key_ok,
            detail=(
                "key is present in the environment"
                if key_ok
                else f"no key found - add {KEY_ENV_VAR} to .env (the value is never displayed)"
            ),
            action=None if key_ok else f"add {KEY_ENV_VAR}=<your key> to .env",
        )
    )

    live_ok = observations > 0
    if live_ok:
        live_detail = f"{observations:,} price observations captured"
        live_action = None
    elif last_run is not None and last_run.status == "failed":
        live_detail = (
            "no live prices yet - the last capture failed; data.gov.in can be very slow, "
            "so retry (the connector now waits up to 120s per request and retries)"
        )
        live_action = FIRST_INGEST_COMMAND
    elif last_run is not None and last_run.status == "ok" and last_run.accepted == 0:
        live_detail = "no live prices yet - the last capture ran but returned zero rows"
        live_action = FIRST_INGEST_COMMAND
    else:
        live_detail = "no live prices yet - no successful capture has run"
        live_action = FIRST_INGEST_COMMAND
    steps.append(
        SetupStep(
            key="live_data",
            label="Live prices ingested",
            ok=live_ok,
            detail=live_detail,
            action=live_action,
        )
    )

    return steps
