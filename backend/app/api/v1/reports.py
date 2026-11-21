"""
Report API endpoints — calendar-based collection metrics.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from io import BytesIO, StringIO
import csv

from app.core.permissions import Permission, require_permissions
from app.dependencies import DBSession
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.report_service import ReportService

router = APIRouter()


@router.get("/range", response_model=ApiResponse)
async def range_report(
    db: DBSession,
    start_date: date = Query(...),
    end_date: date = Query(...),
    report_type: str = Query("daily"),
    current_user: User = Depends(require_permissions(Permission.REPORTS_READ)),
):
    """Generate a date-bounded report from the Finance and Chitti ledgers."""
    data = await ReportService(db).get_range_report(start_date, end_date, report_type)
    return ApiResponse(data=data)


@router.get("/range/export")
async def export_range_report(
    db: DBSession,
    start_date: date = Query(...),
    end_date: date = Query(...),
    report_type: str = Query("daily"),
    file_format: str = Query("csv", pattern="^(csv|xlsx)$"),
    current_user: User = Depends(require_permissions(Permission.REPORTS_READ)),
):
    data = await ReportService(db).get_range_report(start_date, end_date, report_type)
    transactions = [{"record_type": "TRANSACTION", **row} for row in data["transactions"]]
    pending = [{"record_type": "PENDING_DUE", **row} for row in data["pending_details"]]
    rows = [{
        "record_type": "SUMMARY",
        **{key: data[key] for key in ("report_type", "start_date", "end_date", "collected_total", "finance_collected", "chitti_collected", "finance_pending", "chitti_pending")},
    }] + [
        {"record_type": "BREAKDOWN", **row} for row in data.get("breakdown", [])
    ] + transactions + pending
    if not rows:
        rows = [{"record_type": "INFO", "message": "No matching records"}]
    columns = list(dict.fromkeys(key for row in rows for key in row))
    if file_format == "csv":
        text = StringIO(newline="")
        writer = csv.DictWriter(text, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        output = BytesIO(("\ufeff" + text.getvalue()).encode("utf-8"))
        return StreamingResponse(output, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={report_type}-{start_date}-{end_date}.csv"})
    from openpyxl import Workbook
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    for key in ("report_type", "start_date", "end_date", "collected_total", "finance_collected", "chitti_collected", "finance_pending", "chitti_pending"):
        summary.append([key, data[key]])
    for title, section in (("Breakdown", data.get("breakdown", [])), ("Transactions", transactions), ("Pending dues", pending)):
        sheet = workbook.create_sheet(title)
        section_columns = list(dict.fromkeys(key for row in section for key in row)) or ["message"]
        sheet.append(section_columns)
        for row in section:
            sheet.append([str(row.get(column, "")) if isinstance(row.get(column), (dict, list)) else row.get(column) for column in section_columns])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={report_type}-{start_date}-{end_date}.xlsx"})


@router.get("/daily", response_model=ApiResponse)
async def daily_report(
    db: DBSession,
    report_date: Optional[date] = Query(None, alias="date"),
    current_user: User = Depends(require_permissions(Permission.REPORTS_READ)),
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
    current_user: User = Depends(require_permissions(Permission.REPORTS_READ)),
):
    """Headline metrics only for a calendar day (lighter weight)."""
    svc = ReportService(db)
    data = await svc.get_daily_summary(report_date)
    return ApiResponse(data=data)


@router.get("/chitti-plans/{plan_id}/metrics", response_model=ApiResponse)
async def chitti_plan_metrics(
    plan_id: UUID,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.CHITTI_READ)),
):
    """Aggregate metrics for every chitti spawned from a plan."""
    svc = ReportService(db)
    data = await svc.get_chitti_plan_metrics(plan_id)
    return ApiResponse(data=data)
