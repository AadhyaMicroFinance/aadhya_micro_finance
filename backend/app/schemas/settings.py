"""
Settings schemas.
"""

from pydantic import BaseModel
from typing import Any, Optional


class SettingUpdate(BaseModel):
    """Update a setting by key."""

    value: Any
    description: Optional[str] = None


class SettingResponse(BaseModel):
    key: str
    value: Any
    description: Optional[str] = None
    updated_at: str

    model_config = {"from_attributes": True}
