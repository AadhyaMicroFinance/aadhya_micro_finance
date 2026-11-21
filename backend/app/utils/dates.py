"""Date helpers shared by finance and chitti schedule generation."""

from calendar import monthrange
from datetime import date


def add_months(value: date, months: int) -> date:
    """Return ``value`` shifted by whole calendar months.

    Month-end dates are clamped to the last valid day of the target month so a
    monthly schedule never drifts by one day (the old 30-day approximation
    turned 1 September into 31 October).
    """
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
