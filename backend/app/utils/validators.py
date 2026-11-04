"""
Input validation helpers.
"""

import re


def validate_mobile_number(number: str) -> bool:
    """Validate Indian mobile number format."""
    cleaned = re.sub(r"[\s\-\+]", "", number)
    if cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    return bool(re.match(r"^[6-9]\d{9}$", cleaned))


def validate_email(email: str) -> bool:
    """Basic email validation."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def sanitize_string(value: str) -> str:
    """Remove potentially dangerous characters from string input."""
    # Remove null bytes
    return value.replace("\x00", "")
