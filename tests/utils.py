"""Time helpers for tests.

Tests must not hardcode dates like "2026-07-21T10:00:00+03:00" - such a
test starts failing the moment that date is in the past. Everything here
is computed relative to "now" instead, so the suite works on any day.

All helpers return timezone-aware datetimes in the business timezone,
which is what the API requires for start_time.
"""

from datetime import date, datetime, time, timedelta

from app.services.appointment_service import BUSINESS_TIMEZONE


def local_today() -> date:
    return datetime.now(BUSINESS_TIMEZONE).date()


def at(hour: int, minute: int = 0, days_ahead: int = 1) -> datetime:
    """Wall-clock time on a future business day, e.g. at(10, 30) -> tomorrow 10:30 local."""
    day = local_today() + timedelta(days=days_ahead)
    return datetime.combine(day, time(hour, minute), tzinfo=BUSINESS_TIMEZONE)


def past_at(hour: int = 10, minute: int = 0, days_back: int = 1) -> datetime:
    return at(hour, minute, days_ahead=-days_back)


def iso(dt: datetime) -> str:
    """Format for JSON request bodies."""
    return dt.isoformat()
