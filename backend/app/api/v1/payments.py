"""
Payment API endpoints.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.core.permissions import Permission, require_permissions
from app.dependencies import CurrentUser, DBSession
from app.schemas.payment import PaymentCreate, PaymentReversalRequest, PaymentResponse, DueInfo
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.payment_service import PaymentService

router = APIRouter()


@router.post("/", response_model=ApiResponse)
async def record_payment(
    body: PaymentCreate,
    db: DBSession,
    request: Request,
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_CREATE),
):
    """Record a new payment. Atomic operation."""
    service = PaymentService(db)
    payment = await service.record_payment(
        customer_id=body.customer_id,
        finance_account_id=body.finance_account_id,
        chitti_account_id=body.chitti_account_id,
        finance_schedule_id=body.finance_schedule_id,
        chitti_schedule_id=body.chitti_schedule_id,
        amount=body.amount,
        payment_method=body.payment_method,
        payment_date=body.payment_date,
        reference_number=body.reference_number,
        notes=body.notes,
        idempotency_key=body.idempotency_key,
        collected_by=current_user.id,
    )
    return ApiResponse(data=payment)


@router.get("/", response_model=PaginatedResponse)
async def list_payments(
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    customer_id: Optional[str] = None,
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_READ),
):
    """List payment transactions with pagination."""
    from app.repositories.payment_repo import PaymentRepository

    repo = PaymentRepository(db)
    filters = {}
    if customer_id:
        filters["customer_id"] = UUID(customer_id)

    skip = (page - 1) * per_page
    payments, total = await repo.get_all(skip=skip, limit=per_page, filters=filters)

    items = [
        {
            "id": str(p.id),
            "transaction_id": p.transaction_id,
            "customer_id": str(p.customer_id),
            "amount": float(p.amount),
            "payment_method": p.payment_method,
            "payment_date": str(p.payment_date),
            "status": p.status,
            "is_reversal": p.is_reversal,
            "created_at": str(p.created_at),
        }
        for p in payments
    ]
    return PaginatedResponse(
        data=items,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.get("/due/{customer_id}", response_model=ApiResponse)
async def get_due_info(
    customer_id: UUID,
    db: DBSession,
    finance_account_id: str = Query(...),
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_READ),
):
    """Get amount due and outstanding for an account."""
    service = PaymentService(db)
    due_info = await service.get_due_info(str(customer_id), finance_account_id)
    return ApiResponse(data=due_info)


@router.post("/{payment_id}/reverse", response_model=ApiResponse)
async def reverse_payment(
    payment_id: UUID,
    body: PaymentReversalRequest,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_REVERSE),
):
    """Reverse a payment. Creates a reversal transaction."""
    service = PaymentService(db)
    result = await service.reverse_payment(
        payment_id,
        reversal_reason=body.reversal_reason,
        reversed_by=current_user.id,
    )
    return ApiResponse(data=result)
