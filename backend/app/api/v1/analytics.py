"""
Analytics API endpoints — Chitti financial control centre.

Every figure is computed from the chitti ledger, period schedules and member
contributions. Date range, chitti, member and payment mode apply to the whole
overview. ``status`` is a member-status filter and applies to member rows only;
KPIs and charts intentionally continue to report all ledger activity so they
cannot be distorted by the selected member view.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.permissions import Permission, require_permissions
from app.dependencies import DBSession
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.analytics_service import ChittiAnalyticsService

router = APIRouter()


@router.get("/chitti/overview", response_model=ApiResponse)
async def chitti_analytics_overview(
    db: DBSession,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    chitti_id: Optional[UUID] = Query(None),
    member_id: Optional[UUID] = Query(None),
    payment_mode: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_permissions(Permission.CHITTI_READ)),
):
    """Complete dashboard payload: KPIs, daily/monthly series, distributions,
    chitti-wise metrics, member-wise tracking, pending/overdue and ledger."""
    svc = ChittiAnalyticsService(db)
    data = await svc.get_overview(
        start_date=start_date,
        end_date=end_date,
        chitti_id=chitti_id,
        member_id=member_id,
        payment_mode=payment_mode,
        status=status,
    )
    return ApiResponse(data=data)


@router.get("/chitti/transactions", response_model=PaginatedResponse)
async def chitti_analytics_transactions(
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    search: Optional[str] = Query(None),
    chitti_id: Optional[UUID] = Query(None),
    member_id: Optional[UUID] = Query(None),
    payment_mode: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(require_permissions(Permission.CHITTI_READ)),
):
    """Paginated chitti transaction ledger with search and filters."""
    svc = ChittiAnalyticsService(db)
    items, total = await svc.get_ledger(
        page=page,
        per_page=per_page,
        search=search,
        chitti_id=chitti_id,
        member_id=member_id,
        payment_mode=payment_mode,
        start_date=start_date,
        end_date=end_date,
    )
    return PaginatedResponse(
        data=items,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )
