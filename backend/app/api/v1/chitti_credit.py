"""Chitti credit, excess resolution, over-allocation and refund endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.permissions import Permission, require_permissions
from app.dependencies import DBSession
from app.models.user import User
from app.schemas.chitti import (
    ChittiCreditApplication,
    ChittiCreditReversal,
    ChittiExcessResolution,
    ChittiOverallocationResolution,
    ChittiRefundRequest,
)
from app.schemas.common import ApiResponse
from app.services.chitti_credit_service import ChittiCreditService

router = APIRouter()


@router.get("/customers/{customer_id}/credit", response_model=ApiResponse)
async def get_customer_credit(
    customer_id: UUID,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.CHITTI_READ)),
):
    svc = ChittiCreditService(db)
    return ApiResponse(data=await svc.get_customer_credit(customer_id))


@router.post("/{chitti_id}/credit-applications", response_model=ApiResponse)
async def apply_credit(
    chitti_id: UUID,
    body: ChittiCreditApplication,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.PAYMENTS_CREATE)),
):
    svc = ChittiCreditService(db)
    result = await svc.apply_credit(
        chitti_id,
        member_id=body.member_id,
        source_receipt_id=body.source_receipt_id,
        source_period_number=body.source_period_number,
        target_period_number=body.target_period_number,
        amount=body.amount,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        created_by=current_user.id,
    )
    return ApiResponse(data=result)


@router.post(
    "/{chitti_id}/credit-applications/{utilization_id}/reverse",
    response_model=ApiResponse,
)
async def reverse_credit_application(
    chitti_id: UUID,
    utilization_id: UUID,
    body: ChittiCreditReversal,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.PAYMENTS_REVERSE)),
):
    svc = ChittiCreditService(db)
    result = await svc.reverse_credit_utilization(
        chitti_id, utilization_id, reason=body.reason, reversed_by=current_user.id
    )
    return ApiResponse(data=result)


@router.post("/{chitti_id}/excess-resolutions", response_model=ApiResponse)
async def resolve_excess(
    chitti_id: UUID,
    body: ChittiExcessResolution,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.PAYMENTS_CREATE)),
):
    svc = ChittiCreditService(db)
    result = await svc.resolve_excess(
        chitti_id,
        member_id=body.member_id,
        source_receipt_id=body.source_receipt_id,
        amount=body.amount,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        created_by=current_user.id,
    )
    return ApiResponse(data=result)


@router.post(
    "/{chitti_id}/excess-resolutions/{resolution_id}/reverse",
    response_model=ApiResponse,
)
async def reverse_excess_resolution(
    chitti_id: UUID,
    resolution_id: UUID,
    body: ChittiCreditReversal,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.PAYMENTS_REVERSE)),
):
    svc = ChittiCreditService(db)
    result = await svc.reverse_excess_resolution(
        chitti_id, resolution_id, reason=body.reason, reversed_by=current_user.id
    )
    return ApiResponse(data=result)


@router.get(
    "/{chitti_id}/members/{member_id}/overallocations", response_model=ApiResponse
)
async def list_overallocations(
    chitti_id: UUID,
    member_id: UUID,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.CHITTI_READ)),
):
    svc = ChittiCreditService(db)
    return ApiResponse(data=await svc.list_overallocations(chitti_id, member_id))


@router.post("/{chitti_id}/overallocation-resolutions", response_model=ApiResponse)
async def resolve_overallocation(
    chitti_id: UUID,
    body: ChittiOverallocationResolution,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.PAYMENTS_CREATE)),
):
    svc = ChittiCreditService(db)
    result = await svc.resolve_overallocation(
        chitti_id,
        member_id=body.member_id,
        source_period_number=body.source_period_number,
        source_receipt_id=body.source_receipt_id,
        mode=body.mode,
        amount=body.amount,
        target_period_number=body.target_period_number,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        created_by=current_user.id,
    )
    return ApiResponse(data=result)


@router.post(
    "/{chitti_id}/overallocation-resolutions/{resolution_id}/reverse",
    response_model=ApiResponse,
)
async def reverse_overallocation_resolution(
    chitti_id: UUID,
    resolution_id: UUID,
    body: ChittiCreditReversal,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.PAYMENTS_REVERSE)),
):
    svc = ChittiCreditService(db)
    result = await svc.reverse_overallocation_resolution(
        chitti_id, resolution_id, reason=body.reason, reversed_by=current_user.id
    )
    return ApiResponse(data=result)


@router.post("/{chitti_id}/refunds", response_model=ApiResponse)
async def record_refund(
    chitti_id: UUID,
    body: ChittiRefundRequest,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.PAYMENTS_CREATE)),
):
    svc = ChittiCreditService(db)
    result = await svc.refund(
        chitti_id,
        source_receipt_id=body.source_receipt_id,
        source_bucket=body.source_bucket,
        source_member_id=body.source_member_id,
        source_period_number=body.source_period_number,
        amount=body.amount,
        refund_method=body.refund_method,
        reference_number=body.reference_number,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        created_by=current_user.id,
    )
    return ApiResponse(data=result)


@router.get("/{chitti_id}/refunds", response_model=ApiResponse)
async def list_refunds(
    chitti_id: UUID,
    db: DBSession,
    receipt_id: UUID | None = Query(None),
    current_user: User = Depends(require_permissions(Permission.CHITTI_READ)),
):
    svc = ChittiCreditService(db)
    return ApiResponse(
        data=await svc.list_refunds(chitti_id, receipt_id=receipt_id)
    )
