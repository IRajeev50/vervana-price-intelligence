"""Flood Hub seam: pure riverine-severity overlay + honest access-pending scaffold.

No network. The severity reduction is model-independent and tested against the
verified Severity enum; the live gauge discovery stays inert (raises, stores
nothing) until an API key exists.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from vervana.config import Settings
from vervana.supply.feeds import collect_feed_status
from vervana.supply.floodhub import (
    FloodHubClient,
    GaugeFloodStatus,
    overlay_from_statuses,
)
from vervana.supply.scaffold import PartnerAccessPending

_T = datetime(2026, 11, 14, 6, 0, tzinfo=UTC)


def _s(gid: str, sev: str, *, trend: str = "RISE", has_model: bool = True):
    return GaugeFloodStatus(
        gauge_id=gid,
        severity=sev,
        trend=trend,
        issued_time=_T,
        valid_from=date(2026, 11, 14),
        valid_to=date(2026, 11, 21),
        has_model=has_model,
    )


def test_overlay_takes_worst_modelled_severity():
    o = overlay_from_statuses(
        "nashik-onion", [_s("g1", "NO_FLOODING"), _s("g2", "ABOVE_NORMAL"), _s("g3", "SEVERE")]
    )
    assert o is not None
    assert o.severity == "SEVERE"  # worst wins
    assert o.is_risk is True


def test_unknown_and_unmodelled_gauges_are_ignored_not_treated_as_safe():
    # A zone with only UNKNOWN / no-model gauges yields None, NOT "NO_FLOODING".
    o = overlay_from_statuses(
        "agra-potato", [_s("g1", "UNKNOWN"), _s("g2", "EXTREME", has_model=False)]
    )
    assert o is None
    # NO_FLOODING is a real reading and is kept (not a risk, but present).
    o2 = overlay_from_statuses("agra-potato", [_s("g1", "NO_FLOODING")])
    assert o2 is not None and o2.severity == "NO_FLOODING" and o2.is_risk is False


def test_empty_zone_returns_none():
    assert overlay_from_statuses("x", []) is None


def _unset_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.delenv("VERVANA_FLOODHUB_API_KEY", raising=False)
    return Settings()


def test_scaffold_access_pending_fetches_nothing(monkeypatch: pytest.MonkeyPatch):
    client = FloodHubClient(_unset_settings(monkeypatch))
    s = client.status()
    assert s.layer == "scaffold"
    assert "access pending" in s.state
    assert client.configured() is False
    with pytest.raises(PartnerAccessPending):
        client.fetch_overlays([])


def test_feed_registry_lists_floodhub_as_scaffold(monkeypatch: pytest.MonkeyPatch):
    feeds = {f.name: f for f in collect_feed_status(_unset_settings(monkeypatch))}
    assert "google-floodhub" in feeds
    assert feeds["google-floodhub"].layer == "scaffold"
    assert "riverine" in feeds["google-floodhub"].emits.lower()


def test_overlay_repository_round_trip(session):
    from vervana.repository.flood_overlay import (
        latest_overlay_for_zone,
        overlay_count,
        record_overlays,
    )

    o = overlay_from_statuses("nashik-onion", [_s("g1", "ABOVE_NORMAL")])
    assert record_overlays(session, [o]) == {"added": 1, "updated": 0}
    assert overlay_count(session) == 1
    # Same (zone, issued_time) -> update, not duplicate.
    o2 = overlay_from_statuses("nashik-onion", [_s("g1", "SEVERE")])
    assert record_overlays(session, [o2]) == {"added": 0, "updated": 1}
    assert overlay_count(session) == 1
    row = latest_overlay_for_zone(session, "nashik-onion")
    assert row.severity == "SEVERE"
