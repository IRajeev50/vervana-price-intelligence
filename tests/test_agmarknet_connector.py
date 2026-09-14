"""Agmarknet connector: field mapping, validation, canonical conversion, ingest_run."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vervana.connectors.agmarknet import (
    SOURCE_URL,
    AgmarknetConnector,
    SchemaError,
    map_fields,
)
from vervana.models.ingest import IngestRun
from vervana.models.observations import PriceObservation
from vervana.repository.registry import seed_registry

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "agmarknet_sample.json"
SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_registry(session, SEED_DIR)
    return session


def _records() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]


def test_map_fields_case_insensitive():
    rec = {
        "State": "Delhi",
        "Market": "Azadpur",
        "Commodity": "Onion",
        "Arrival_Date": "09/09/2026",
        "Min_Price": "2100",
        "Max_Price": "2500",
        "Modal_Price": "2300",
    }
    fields = map_fields(rec)
    assert fields["market"] == "Azadpur"
    assert fields["modal_price"] == "2300"


def test_map_fields_missing_required_fails_loudly():
    with pytest.raises(SchemaError, match="missing required"):
        map_fields({"market": "Azadpur", "commodity": "Potato"})  # no prices/date


def test_modal_outside_range_is_accepted_without_point(seeded: Session):
    # Real Agmarknet data sometimes reports a modal outside [min, max]. We must NOT crash
    # (ck_point_within_range) — the row is kept with the range but no asserted point price.
    from sqlalchemy import select

    rec = {
        "state": "Delhi",
        "district": "Delhi",
        "market": "Azadpur",
        "commodity": "Potato",
        "variety": "Local",
        "grade": "FAQ",
        "arrival_date": "10/09/2026",
        "min_price": "1500",
        "max_price": "2000",
        "modal_price": "1000",  # modal < min!
    }
    result = AgmarknetConnector().ingest(seeded, [rec], mode="test")
    assert result.accepted == 1  # accepted, not crashed
    obs = seeded.scalars(select(PriceObservation)).all()
    assert len(obs) == 1
    assert obs[0].price_point_paise is None  # the out-of-range modal is not asserted
    assert obs[0].price_low_paise == 150000 and obs[0].price_high_paise == 200000
    # canonical falls back to the midpoint (1750/quintal -> 17.5/kg -> 1750 paise/kg)
    assert obs[0].canonical_price_paise_per_kg == 1750


def test_ingest_accepts_good_rejects_bad(seeded: Session):
    result = AgmarknetConnector().ingest(seeded, _records(), mode="test")
    assert result.rows_in == 8
    # 3 good: Azadpur Potato, Azadpur Onion, Keshopur Potato, plus mixed-case Onion = 4
    assert result.accepted == 4
    reasons = result.reason_counts
    assert any("missing_or_zero_price" in r for r in reasons)
    assert any("unresolved_commodity" in r for r in reasons)  # Dragon Fruit
    assert any("unresolved_market" in r for r in reasons)  # Some Random Mandi
    assert any("range_disorder" in r for r in reasons)  # min>max


def test_ingest_skips_exact_duplicates(seeded: Session):
    # A recurring capture over the lookback window re-fetches already-stored days;
    # those rows must be skipped, never double-counted.
    first = AgmarknetConnector().ingest(seeded, _records(), mode="test")
    assert first.accepted == 4
    second = AgmarknetConnector().ingest(seeded, _records(), mode="test")
    assert second.accepted == 0
    assert second.reason_counts.get("duplicate_already_ingested") == 4
    # still exactly one stored observation per unique row
    assert seeded.scalar(select(func.count()).select_from(PriceObservation)) == 4


def test_canonical_quintal_to_kg(seeded: Session):
    AgmarknetConnector().ingest(
        seeded, _records()[:1], mode="test"
    )  # Azadpur Potato modal 1350/qtl
    obs = seeded.scalars(select(PriceObservation)).all()
    assert len(obs) == 1
    o = obs[0]
    assert o.unit_raw == "Quintal"
    assert o.price_point_paise == 135000  # 1350 rupees/quintal in paise
    assert o.canonical_price_paise_per_kg == 1350  # /100 kg = 13.50 rupees/kg
    assert o.source_url == SOURCE_URL
    assert SOURCE_URL.startswith("https://api.agmarknet.gov.in/v1/")
    assert "Potato" in o.raw_quote


def test_run_records_ingest_run(seeded: Session):
    connector = AgmarknetConnector(raw_dir=Path("/tmp/vervana_test_raw"))
    connector.fetch_raw = lambda **_: _records()  # bypass network
    run, result = connector.run(seeded, mode="daily")
    assert run.status == "ok"
    assert run.rows_in == 8
    assert run.accepted == 4
    assert run.rejection_reasons  # dict of reason->count persisted


def test_fetch_failure_leaves_no_partial_data(seeded: Session):
    connector = AgmarknetConnector()

    def boom(**_):
        raise RuntimeError("network down")

    connector.fetch_raw = boom
    with pytest.raises(RuntimeError, match="network down"):
        connector.run(seeded, mode="daily")
    # No observations written, and the failed run is recorded.
    assert seeded.scalar(select(func.count()).select_from(PriceObservation)) == 0
    failed = seeded.scalars(select(IngestRun).where(IngestRun.status == "failed")).all()
    assert len(failed) == 1
    assert "network down" in failed[0].error


def test_connector_disabled_via_config(monkeypatch):
    from vervana.config import Settings

    monkeypatch.setenv("VERVANA_DISABLED_CONNECTORS", "agmarknet,youtube")
    settings = Settings(_env_file=None)
    assert AgmarknetConnector().enabled(settings) is False


# ---------------------------------------------------------------------------
# Network resilience: the Agmarknet 2.0 API can be slow, so timeouts/transport
# errors are retried within a bounded budget instead of killing the run.
# Every fetch makes one filters call (state lookup) plus one report call per day.
# ---------------------------------------------------------------------------


class _StubResponse:
    def __init__(self, status_code=200, payload=None, body_raises=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"data": {}}
        self._body_raises = body_raises

    def json(self):
        if self._body_raises:
            raise ValueError("not json")
        return self._payload

    def raise_for_status(self):
        import httpx

        raise httpx.HTTPStatusError(f"status {self.status_code}", request=None, response=None)


class _FlakyClient:
    """Stands in for httpx.Client: plays a scripted list of outcomes per GET."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _filters_payload():
    return {"data": {"state_data": [{"state_id": 25, "state_name": "NCT of Delhi"}]}}


def _report_payload():
    return {
        "success": True,
        "commodityGroups": [
            {
                "CommodityGroup": "Vegetables",
                "commodities": [
                    {
                        "commodityName": "Onion",
                        "markets": [
                            {
                                "marketCenter": "APMC Azadpur",
                                "total_arrivals": 861.0,
                                "data": [
                                    {
                                        "arrivals": 861.0,
                                        "unitOfArrivals": "Metric Tonnes",
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


def _settings(**overrides):
    from vervana.config import Settings

    overrides.setdefault("agmarknet_lookback_days", 1)
    return Settings(_env_file=None, **overrides)


_TODAY = date(2026, 9, 13)


def test_fetch_retries_read_timeout_then_succeeds(monkeypatch):
    import httpx

    from vervana.connectors import agmarknet as mod

    client = _FlakyClient(
        [
            httpx.ReadTimeout("slow server"),
            _StubResponse(200, _filters_payload()),
            _StubResponse(200, _report_payload()),
        ]
    )
    monkeypatch.setattr(mod.httpx, "Client", client)
    sleeps: list[float] = []
    records = AgmarknetConnector().fetch_raw(settings=_settings(), sleep=sleeps.append, today=_TODAY)
    assert client.calls == 3  # one timed-out filters attempt, filters, then the report
    assert sleeps == [2.0]  # backoff_base * 2**0, from settings default
    assert records == [
        {
            "state": "NCT of Delhi",
            "district": "",
            "market": "Azadpur",  # "APMC Azadpur" translated to the registry alias
            "commodity": "Onion",
            "variety": "Onion",
            "grade": "",
            "arrival_date": "2026-09-13",
            "min_price": "2000.0",
            "max_price": "4500.0",
            "modal_price": "3281.0",
        }
    ]


def test_fetch_exhausts_retries_with_clear_error(monkeypatch):
    import httpx

    from vervana.connectors import agmarknet as mod
    from vervana.connectors.agmarknet import FetchError

    client = _FlakyClient([httpx.ReadTimeout("slow server")] * 4)
    monkeypatch.setattr(mod.httpx, "Client", client)
    sleeps: list[float] = []
    with pytest.raises(FetchError) as excinfo:
        AgmarknetConnector().fetch_raw(settings=_settings(), sleep=sleeps.append, today=_TODAY)
    msg = str(excinfo.value)
    assert "VERVANA_AGMARKNET_TIMEOUT_SECONDS" in msg
    assert "ReadTimeout" in msg
    assert client.calls == 4  # default VERVANA_AGMARKNET_MAX_RETRIES
    assert sleeps == [2.0, 4.0, 8.0, 16.0]  # capped exponential backoff


def test_fetch_retries_non_json_200(monkeypatch):
    from vervana.connectors import agmarknet as mod

    client = _FlakyClient(
        [
            _StubResponse(200, body_raises=True),  # WAF HTML page with a 200
            _StubResponse(200, _filters_payload()),
            _StubResponse(200, _report_payload()),
        ]
    )
    monkeypatch.setattr(mod.httpx, "Client", client)
    records = AgmarknetConnector().fetch_raw(settings=_settings(), sleep=lambda s: None, today=_TODAY)
    assert len(records) == 1
    assert client.calls == 3


def test_fetch_4xx_fails_immediately_without_retry(monkeypatch):
    from vervana.connectors import agmarknet as mod

    client = _FlakyClient([_StubResponse(403)] * 4)
    monkeypatch.setattr(mod.httpx, "Client", client)
    import httpx

    with pytest.raises(httpx.HTTPStatusError):
        AgmarknetConnector().fetch_raw(settings=_settings(), sleep=lambda s: None, today=_TODAY)
    assert client.calls == 1  # 4xx is not retried


def test_fetch_unknown_state_fails_loudly(monkeypatch):
    from vervana.connectors import agmarknet as mod
    from vervana.connectors.agmarknet import FetchError

    client = _FlakyClient(
        [_StubResponse(200, {"data": {"state_data": [{"state_id": 1, "state_name": "Goa"}]}})]
    )
    monkeypatch.setattr(mod.httpx, "Client", client)
    with pytest.raises(FetchError, match="could not resolve state"):
        AgmarknetConnector().fetch_raw(settings=_settings(), sleep=lambda s: None, today=_TODAY)
    assert client.calls == 1  # a bad state name is not retried


def test_fetch_404_day_is_skipped_not_fatal(monkeypatch):
    from vervana.connectors import agmarknet as mod

    client = _FlakyClient(
        [
            _StubResponse(200, _filters_payload()),
            _StubResponse(404),  # nothing reported on the 13th
            _StubResponse(200, _report_payload()),  # the 12th has data
        ]
    )
    monkeypatch.setattr(mod.httpx, "Client", client)
    records = AgmarknetConnector().fetch_raw(
        settings=_settings(agmarknet_lookback_days=2), sleep=lambda s: None, today=_TODAY
    )
    assert client.calls == 3
    assert [r["arrival_date"] for r in records] == ["2026-09-12"]


def test_fetch_translates_agmarknet2_display_names(monkeypatch):
    from vervana.connectors import agmarknet as mod

    payload = _report_payload()
    payload["commodityGroups"][0]["commodities"][0]["commodityName"] = "Ginger(Green)"
    client = _FlakyClient([_StubResponse(200, _filters_payload()), _StubResponse(200, payload)])
    monkeypatch.setattr(mod.httpx, "Client", client)
    records = AgmarknetConnector().fetch_raw(settings=_settings(), sleep=lambda s: None, today=_TODAY)
    assert records[0]["commodity"] == "Ginger"  # registry seed name, not the 2.0 display name
    assert records[0]["market"] == "Azadpur"


def test_network_budget_comes_from_settings(monkeypatch):
    from vervana.config import Settings

    monkeypatch.setenv("VERVANA_AGMARKNET_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("VERVANA_AGMARKNET_MAX_RETRIES", "6")
    monkeypatch.setenv("VERVANA_AGMARKNET_LOOKBACK_DAYS", "3")
    s = Settings(_env_file=None)
    assert s.agmarknet_timeout_seconds == 300.0
    assert s.agmarknet_max_retries == 6
    assert s.agmarknet_lookback_days == 3


def test_record_failure_persists_failed_run(session: Session):
    connector = AgmarknetConnector()
    run = connector.record_failure(session, mode="daily", exc=ValueError("boom"))
    assert run.status == "failed"
    assert "boom" in run.error
    failed = session.scalars(select(IngestRun).where(IngestRun.status == "failed")).all()
    assert len(failed) == 1
