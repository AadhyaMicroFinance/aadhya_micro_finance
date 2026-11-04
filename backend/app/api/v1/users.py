"""
User management API endpoints.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.permissions import Permission, require_permissions
from app.dependencies import CurrentUser, DBSession
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.user_service import UserService

router = APIRouter()


@router.post("/", response_model=ApiResponse)
async def create_user(
    body: UserCreate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.USERS_WRITE),
):
    """Create a new user (Super Admin only)."""
    service = UserService(db)
    user = await service.create_user(
        username=body.username,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=body.role,
    )
    return ApiResponse(data=user)


@router.get("/", response_model=PaginatedResponse)
async def list_users(
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    role: Optional[str] = None,
    current_user: CurrentUser = require_permissions(Permission.USERS_READ),
):
    """List all users with pagination."""
    service = UserService(db)
    items, total = await service.list_users(page=page, per_page=per_page, role=role)
    return PaginatedResponse(
        data=items,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.get("/{user_id}", response_model=ApiResponse)
async def get_user(
    user_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.USERS_READ),
):
    """Get a user by ID."""
    service = UserService(db)
    user = await service.get_user(user_id)
    return ApiResponse(data=user)


@router.put("/{user_id}", response_model=ApiResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.USERS_WRITE),
):
    """Update a user."""
    service = UserService(db)
    user = await service.update_user(
        user_id,
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        is_active=body.is_active,
    )
    return ApiResponse(data=user)


@router.delete("/{user_id}", response_model=ApiResponse)
async def delete_user(
    user_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.USERS_DELETE),
):
    """Deactivate a user."""
    service = UserService(db)
    await service.delete_user(user_id)
    return ApiResponse(data={"message": "User deactivated successfully."})
