"""Time handling policy, enforced in one place (Part 7).

Rules:
  * Store UTC.
  * Display IST (Asia/Kolkata).
  * No naive datetimes are ever accepted — a datetime without tzinfo is a bug,
    because an estimated timestamp must never be indistinguishable from a real
    one, and a naive timestamp hides which zone it meant.

These helpers are foundational (used by every connector and the data model), so
they are written and tested at M0 even though nothing else exists yet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class NaiveDatetimeError(ValueError):
    """Raised when a naive (tzinfo-less) datetime is supplied where tz-aware is required."""


def ensure_aware(dt: datetime) -> datetime:
    """Return `dt` unchanged if timezone-aware; raise if naive.

    This is the gate every datetime must pass before it is stored or converted.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise NaiveDatetimeError(
            "Naive datetime rejected: attach tzinfo (UTC for storage, IST for display)."
        )
    return dt


def now_utc() -> datetime:
    """Current instant as a tz-aware UTC datetime."""
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    """Convert a tz-aware datetime to UTC. Naive input is rejected."""
    return ensure_aware(dt).astimezone(UTC)


def to_ist(dt: datetime) -> datetime:
    """Convert a tz-aware datetime to IST for display. Naive input is rejected."""
    return ensure_aware(dt).astimezone(IST)


def format_ist(dt: datetime) -> str:
    """Human-readable IST string, e.g. '2026-09-10 14:30:00 IST'."""
    return to_ist(dt).strftime("%Y-%m-%d %H:%M:%S IST")
