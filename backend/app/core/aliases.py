"""Slot alias rules shared by every enrollment path.

The stored alias keeps the operator's original casing. Uniqueness is compared
with ``lower()`` both here and in the PostgreSQL unique index, so an alias such
as "Slot A" and "slot a" are the same slot identity.
"""

from typing import Optional

from app.core.exceptions import BadRequestException


def normalize_slot_alias(
    value: Optional[str], *, error_code: str = "INVALID_ALIAS"
) -> Optional[str]:
    """Trim and validate an alias without rewriting its historical casing."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise BadRequestException("Alias cannot be blank.", error_code=error_code)
    if len(normalized) > 100:
        raise BadRequestException(
            "Alias must be 100 characters or fewer.", error_code=error_code
        )
    return normalized


def alias_lookup_key(value: str) -> str:
    """Case-insensitive comparison key matching PostgreSQL's lower(alias)."""
    return value.lower()
