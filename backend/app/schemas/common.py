"""
Common schema types used across the application.
"""

from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel):
    """Standard API response wrapper."""

    success: bool = True
    data: Any = None
    error: Optional[dict] = None
    meta: Optional[dict] = None


class PaginatedResponse(BaseModel):
    """Paginated list response."""

    success: bool = True
    data: list[Any] = []
    meta: dict = Field(default_factory=lambda: {
        "page": 1,
        "per_page": 25,
        "total": 0,
        "total_pages": 0,
    })


class PaginationParams(BaseModel):
    """Query parameters for pagination."""

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)


class ErrorResponse(BaseModel):
    """Structured error response."""

    success: bool = False
    error: dict = Field(default_factory=lambda: {
        "code": "UNKNOWN_ERROR",
        "message": "An unexpected error occurred.",
    })
