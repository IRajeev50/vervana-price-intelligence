"""Arrivals capture change: store the metric-tonne arrivals Agmarknet co-reports.

Offline. Proves the parse helper's honesty (blank/garbage -> None, genuine 0.0 kept), that
the daily-report flatten carries arrivals, that ingest stores them in the new column (and a
missing figure stays NULL, never a guessed zero), that an unexpected arrivals unit drops the
value but keeps the price row, and that the queryable accessors work.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vervana.connectors.agmarknet import AgmarknetConnector, _arrivals_tonnes, map_fields
from vervana.models.observations import PriceObservation
from vervana.repository.prices import arrivals_coverage, arrivals_series
from vervana.repository.registry import seed_registry

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


# --- parse helper honesty --------------------------------------------------

def test_arrivals_parse_rejects_junk_keeps_genuine_zero():
    assert _arrivals_tonnes("861.0") == 861.0
    assert _arrivals_tonnes("1,234.5") == 1234.5  # thousands separator tolerated
    assert _arrivals_tonnes("0") == 0.0  # a genuine zero reading is kept, not dropped
    assert _arrivals_tonnes("") is None  # not reported -> None, never a guessed zero
    assert _arrivals_tonnes("-") is None
    assert _arrivals_tonnes("NA") is None
    assert _arrivals_tonnes("-5") is None  # negative is garbage, not stored
    assert _arrivals_tonnes("tonnes") is None


def test_map_fields_arrivals_is_optional():
    # No arrivals key -> map_fields still succeeds (arrivals is not REQUIRED).
    fields = map_fields(
        {
            "market": "Azadpur",
            "commodity": "Onion",
            "arrival_date": "10/09/2026",
            "min_price": "2100",
            "max_price": "2500",
            "modal_price": "2300",
        }
    )
    assert "arrivals" not in fields or fields.get("arrivals") in (None, "")


# --- daily-report flatten carries arrivals ---------------------------------

def _report_payload(arrivals=861.0, unit="Metric Tonnes"):
    return {
        "commodityGroups": [
            {
                "commodities": [
                    {
                        "commodityName": "Onion",
                        "markets": [
                            {
                                "marketCenter": "APMC Azadpur",
                                "data": [
                                    {
                                        "arrivals": arrivals,
                                        "unitOfArrivals": unit,
                                        "variety": "Onion",
                                        "minimumPrice": 2000.0,
                                        "maximumPrice": 4500.0,
                                        "modalPrice": 3281.0,
                                        "unitOfPrice": "Rs./Quintal",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_flatten_daily_report_carries_arrivals():
    from datetime import date

    recs = AgmarknetConnector()._flatten_daily_report(
        _report_payload(), "NCT of Delhi", date(2026, 9, 13)
    )
    assert recs[0]["arrivals"] == "861.0"


def test_flatten_drops_arrivals_on_unexpected_unit_but_keeps_row():
    from datetime import date

    recs = AgmarknetConnector()._flatten_daily_report(
        _report_payload(arrivals=50.0, unit="Quintal"), "NCT of Delhi", date(2026, 9, 13)
    )
    assert len(recs) == 1  # the price row survives
    assert recs[0]["arrivals"] == ""  # arrivals dropped (wrong unit) -> NULL downstream
    assert recs[0]["modal_price"] == "3281.0"


# --- ingest stores arrivals ------------------------------------------------

def _rec(arrivals: str | None):
    r = {
        "market": "Azadpur",
        "commodity": "Onion",
        "arrival_date": "2026-09-14",
        "min_price": "2000",
        "max_price": "4500",
        "modal_price": "3281",
    }
    if arrivals is not None:
        r["arrivals"] = arrivals
    return r


def test_ingest_stores_arrivals_tonnes(seeded: Session):
    AgmarknetConnector().ingest(seeded, [_rec("861.0")], mode="test")
    obs = seeded.scalars(select(PriceObservation)).all()
    assert len(obs) == 1
    assert float(obs[0].arrivals_tonnes) == 861.0
    assert arrivals_coverage(seeded) == 1


def test_ingest_without_arrivals_leaves_null_not_zero(seeded: Session):
    AgmarknetConnector().ingest(seeded, [_rec(None)], mode="test")
    obs = seeded.scalars(select(PriceObservation)).all()
    assert len(obs) == 1
    assert obs[0].arrivals_tonnes is None  # not reported -> NULL, never 0
    assert arrivals_coverage(seeded) == 0


def test_arrivals_series_reads_back_captured_rows(seeded: Session):
    AgmarknetConnector().ingest(seeded, [_rec("861.0")], mode="test")
    obs = seeded.scalars(select(PriceObservation)).first()
    series = arrivals_series(seeded, commodity_id=obs.commodity_id, market_id=obs.market_id)
    assert series and series[0][1] == 861.0
