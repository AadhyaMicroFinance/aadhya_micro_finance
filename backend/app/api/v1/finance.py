"""
Finance account API endpoints.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.permissions import Permission, require_permissions
from app.dependencies import CurrentUser, DBSession
from app.schemas.finance import (
    FinanceAccountCreate,
    FinanceAccountUpdate,
    FinanceAccountResponse,
    FinanceScheduleResponse,
)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.finance_service import FinanceService

router = APIRouter()


@router.post("/", response_model=ApiResponse)
async def create_finance_account(
    body: FinanceAccountCreate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.FINANCE_CREATE),
):
    """Create a new finance account and generate payment schedule."""
    service = FinanceService(db)
    account = await service.create_account(
        customer_id=body.customer_id,
        principal_amount=body.principal_amount,
        interest_rate=body.interest_rate,
        interest_type=body.interest_type,
        fees=body.fees,
        frequency=body.frequency,
        start_date=body.start_date,
        first_due_date=body.first_due_date,
        number_of_installments=body.number_of_installments,
        custom_installment_amount=body.custom_installment_amount,
        notes=body.notes,
        created_by=current_user.id,
    )
    return ApiResponse(data=account)


@router.get("/", response_model=PaginatedResponse)
async def list_finance_accounts(
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    current_user: CurrentUser = require_permissions(Permission.FINANCE_READ),
):
    """List finance accounts with pagination."""
    service = FinanceService(db)
    items, total = await service.list_accounts(
        page=page, per_page=per_page, status=status, customer_id=customer_id
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


@router.get("/{account_id}", response_model=ApiResponse)
async def get_finance_account(
    account_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.FINANCE_READ),
):
    """Get a finance account by ID."""
    service = FinanceService(db)
    account = await service.get_account(account_id)
    return ApiResponse(data=account)


@router.get("/{account_id}/schedule", response_model=ApiResponse)
async def get_finance_schedule(
    account_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.FINANCE_READ),
):
    """Get the payment schedule for a finance account."""
    service = FinanceService(db)
    schedule = await service.get_schedule(account_id)
    return ApiResponse(data=schedule)


@router.put("/{account_id}", response_model=ApiResponse)
async def update_finance_account(
    account_id: UUID,
    body: FinanceAccountUpdate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.FINANCE_WRITE),
):
    """Update a finance account."""
    # Placeholder — will be expanded in Phase 4
    return ApiResponse(data={"message": "Update endpoint — to be implemented in Phase 4."})
