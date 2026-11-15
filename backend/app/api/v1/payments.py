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


@router.get("/pending", response_model=ApiResponse)
async def list_pending_payments(
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_READ),
):
    """List due unpaid Finance installments and Chitti contributions."""
    service = PaymentService(db)
    return ApiResponse(data=await service.list_pending_collections())


@router.get("/customer/{customer_id}/eligible-accounts", response_model=ApiResponse)
async def eligible_collection_accounts(
    customer_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_READ),
):
    """Return finance accounts and running Chitti memberships as separate ledgers."""
    from app.repositories.finance_repo import FinanceAccountRepository
    from app.repositories.chitti_repo import (
        ChittiMemberRepository, ChittiRepository, ChittiContributionRepository,
        ChittiPeriodScheduleRepository,
    )
    from app.models.customer import Customer
    customer = await db.get(Customer, customer_id)
    if not customer:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("Customer", customer_id)
    finance_repo = FinanceAccountRepository(db)
    member_repo = ChittiMemberRepository(db)
    chitti_repo = ChittiRepository(db)
    contribution_repo = ChittiContributionRepository(db)
    schedule_repo = ChittiPeriodScheduleRepository(db)
    finance = await finance_repo.get_by_customer_id(customer_id)
    finance_items = [{
        "id": str(a.id), "account_number": a.account_number,
        "installment_amount": float(a.installment_amount), "frequency": a.frequency,
        "status": a.status,
    } for a in finance if a.status == "ACTIVE"]
    memberships = await member_repo.get_by_customer_id(customer_id)
    chitti_items = []
    for member in memberships:
        if member.status != "ACTIVE":
            continue
        chitti = await chitti_repo.get_by_id(member.chitti_id)
        if not chitti or chitti.status != "RUNNING":
            continue
        contributions = await contribution_repo.get_by_member_id(member.id)
        schedules = {s.period_number: s for s in await schedule_repo.get_by_chitti_id(chitti.id)}
        outstanding = [c for c in contributions if c.remaining_amount > 0]
        if not outstanding:
            continue
        contribution = min(outstanding, key=lambda c: c.period_number)
        period = schedules.get(contribution.period_number)
        chitti_items.append({
            "chitti_id": str(chitti.id), "chitti_code": chitti.chitti_code,
            "chitti_name": chitti.name, "member_id": str(member.id),
            "member_number": member.member_number,
            "total_value": float(chitti.total_value),
            "frequency": (chitti.plan_snapshot or {}).get("frequency", "MONTHLY"),
            "current_period": contribution.period_number,
            "due_date": str(period.due_date) if period else None,
            "amount_due": float(contribution.remaining_amount),
            "outstanding": float(sum((c.remaining_amount for c in outstanding), 0)),
            "status": contribution.status,
        })
    return ApiResponse(data={"finance_accounts": finance_items, "chitti_memberships": chitti_items})


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
    """List Finance receipts and Chitti contribution ledger entries together."""
    service = PaymentService(db)
    items, total = await service.list_payment_history(
        page=page,
        per_page=per_page,
        customer_id=UUID(customer_id) if customer_id else None,
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
