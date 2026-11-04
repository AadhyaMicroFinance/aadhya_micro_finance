"""
Report API endpoints — calendar-based collection metrics.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.permissions import Permission, require_permissions
from app.dependencies import CurrentUser, DBSession
from app.schemas.common import ApiResponse
from app.services.report_service import ReportService

router = APIRouter()


@router.get("/daily", response_model=ApiResponse)
async def daily_report(
    db: DBSession,
    report_date: Optional[date] = Query(None, alias="date"),
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_READ),
):
    """Full calendar-day report: headline metrics, by-user collections,
    by-method split, pending details and the day's payments."""
    svc = ReportService(db)
    data = await svc.get_daily_report(report_date)
    return ApiResponse(data=data)


@router.get("/daily/summary", response_model=ApiResponse)
async def daily_summary(
    db: DBSession,
    report_date: Optional[date] = Query(None, alias="date"),
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_READ),
):
    """Headline metrics only for a calendar day (lighter weight)."""
    svc = ReportService(db)
    data = await svc.get_daily_summary(report_date)
    return ApiResponse(data=data)


@router.get("/chitti-plans/{plan_id}/metrics", response_model=ApiResponse)
async def chitti_plan_metrics(
    plan_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    """Aggregate metrics for every chitti spawned from a plan."""
    svc = ReportService(db)
    data = await svc.get_chitti_plan_metrics(plan_id)
    return ApiResponse(data=data)
