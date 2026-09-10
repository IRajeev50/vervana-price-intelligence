"""M7 connectors: eNAM stub, observer independence (R11), context signals, config-disable."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.connectors.context import ContextConnector
from vervana.connectors.enam import EnamAccessUnresolvedError, EnamConnector
from vervana.connectors.observer import ObserverConnector, add_observer
from vervana.db.base import SourceClass
from vervana.models.context import ContextSignal
from vervana.models.observations import PriceObservation
from vervana.repository.registry import seed_registry

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def test_enam_is_stub():
    with pytest.raises(EnamAccessUnresolvedError):
        EnamConnector().fetch_raw()


def test_connectors_disable_via_config(monkeypatch):
    from vervana.config import Settings

    monkeypatch.setenv("VERVANA_DISABLED_CONNECTORS", "enam,observer,context,quickcommerce")
    s = Settings(_env_file=None)
    assert EnamConnector().enabled(s) is False
    assert ObserverConnector().enabled(s) is False
    assert ContextConnector().enabled(s) is False


def test_observer_independence_recorded(seeded: Session):
    conflicted = add_observer(
        seeded, name="Ramesh (agent)", role="commission agent", trades_in_reported=True
    )
    assert conflicted.is_independent is False
    result = ObserverConnector().import_csv(seeded, SAMPLES / "observer_sample.csv")
    assert result.accepted == 2
    obs = seeded.scalars(
        select(PriceObservation).where(
            PriceObservation.source_class == SourceClass.quote_indicative
        )
    ).all()
    assert all(o.observer_id == conflicted.id for o in obs)  # every quote carries the observer


def test_context_signals_are_features_not_prices(seeded: Session):
    result = ContextConnector().import_csv(seeded, SAMPLES / "context_sample.csv")
    assert result.accepted == 3
    # They land in context_signal, NOT price_observation.
    assert seeded.scalar(select(func.count()).select_from(ContextSignal)) == 3
    assert seeded.scalar(select(func.count()).select_from(PriceObservation)) == 0
    types = {c.signal_type for c in seeded.scalars(select(ContextSignal))}
    assert types == {"diesel", "weather", "festival"}
