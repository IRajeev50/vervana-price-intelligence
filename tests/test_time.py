"""Time policy: naive rejected, UTC<->IST round-trips, IST display correct."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vervana.time import (
    IST,
    NaiveDatetimeError,
    ensure_aware,
    format_ist,
    now_utc,
    to_ist,
    to_utc,
)


def test_naive_datetime_rejected() -> None:
    naive = datetime(2026, 9, 10, 14, 30, 0)  # noqa: DTZ001 - intentionally naive
    with pytest.raises(NaiveDatetimeError):
        ensure_aware(naive)
    with pytest.raises(NaiveDatetimeError):
        to_utc(naive)
    with pytest.raises(NaiveDatetimeError):
        to_ist(naive)


def test_now_utc_is_aware_and_utc() -> None:
    n = now_utc()
    assert n.tzinfo is not None
    assert n.utcoffset().total_seconds() == 0


def test_utc_ist_roundtrip() -> None:
    # 09:00 UTC is 14:30 IST (UTC+5:30).
    utc_dt = datetime(2026, 9, 10, 9, 0, 0, tzinfo=UTC)
    ist_dt = to_ist(utc_dt)
    assert ist_dt.hour == 14
    assert ist_dt.minute == 30
    assert ist_dt.tzinfo == IST
    # Round-trip back to UTC is the same instant.
    assert to_utc(ist_dt) == utc_dt


def test_format_ist() -> None:
    utc_dt = datetime(2026, 9, 10, 9, 0, 0, tzinfo=UTC)
    assert format_ist(utc_dt) == "2026-09-10 14:30:00 IST"
