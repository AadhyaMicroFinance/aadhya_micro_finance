"""Administration screens: effective settings, audit trail and WhatsApp log."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.permissions import Permission, require_permissions
from app.dependencies import DBSession
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.admin_service import AdminService

router = APIRouter()


@router.get("/settings", response_model=ApiResponse)
async def get_effective_settings(
    db: DBSession,
    current_user: User = Depends(
        require_permissions(Permission.SETTINGS_READ)
    ),
):
    """Return effective, non-secret settings for the Settings screen."""
    return ApiResponse(data=await AdminService(db).settings_payload())


@router.get("/audit", response_model=PaginatedResponse)
async def list_audit_logs(
    db: DBSession,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    action: Optional[str] = Query(None, max_length=50),
    entity_type: Optional[str] = Query(None, max_length=50),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    current_user: User = Depends(require_permissions(Permission.AUDIT_READ)),
):
    """List audit entries with server-side filtering and pagination."""
    result = await AdminService(db).audit_logs(
        date_from=date_from,
        date_to=date_to,
        action=action,
        entity_type=entity_type,
        page=page,
        per_page=per_page,
    )
    return PaginatedResponse(
        data=result["items"],
        meta={
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "total_pages": result["total_pages"],
        },
    )


@router.get("/whatsapp", response_model=ApiResponse)
async def get_whatsapp_status(
    db: DBSession,
    limit: int = Query(25, ge=1, le=100),
    current_user: User = Depends(
        require_permissions(Permission.WHATSAPP_READ)
    ),
):
    """Return WhatsApp readiness, daily counts and a recent message log."""
    return ApiResponse(data=await AdminService(db).whatsapp_payload(limit=limit))
