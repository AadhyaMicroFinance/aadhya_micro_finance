"""
Timezone utilities.
Default business timezone: Asia/Kolkata (IST).
"""

from datetime import datetime, date, timezone, timedelta

import pytz

from app.config import get_settings

settings = get_settings()
BUSINESS_TZ = pytz.timezone(settings.APP_TIMEZONE)


def now_ist() -> datetime:
    """Get current datetime in business timezone."""
    return datetime.now(BUSINESS_TZ)


def today_ist() -> date:
    """Get current date in business timezone."""
    return now_ist().date()


def to_utc(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to UTC."""
    if dt.tzinfo is None:
        dt = BUSINESS_TZ.localize(dt)
    return dt.astimezone(timezone.utc)


def from_utc(dt: datetime) -> datetime:
    """Convert a UTC datetime to business timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BUSINESS_TZ)


def make_aware(dt: datetime) -> datetime:
    """Make a naive datetime timezone-aware in business timezone."""
    if dt.tzinfo is None:
        return BUSINESS_TZ.localize(dt)
    return dt
