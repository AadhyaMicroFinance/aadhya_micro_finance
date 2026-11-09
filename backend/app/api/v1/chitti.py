"""
Chitti API endpoints — Plans, Instances, Members, Schedule, Contributions, Payouts.
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.core.permissions import Permission, require_permissions
from app.core.exceptions import NotFoundException
from app.dependencies import CurrentUser, DBSession
from app.schemas.chitti import (
    AgreementConfirm,
    ChittiContributionPayment,
    ChittiCreate,
    ChittiMemberAdd,
    ChittiPayoutRecord,
    ChittiPlanCreate,
    ChittiPlanUpdate,
    ChittiPreviewRequest,
    ChittiUpdate,
    MemberCancel,
)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.chitti_service import ChittiService

router = APIRouter()


# ===========================================================================
# Plans
# ===========================================================================


@router.post("/plans", response_model=ApiResponse)
async def create_plan(
    body: ChittiPlanCreate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_CREATE),
):
    svc = ChittiService(db)
    plan = await svc.create_plan(
        data=body.model_dump(), created_by=current_user.id
    )
    return ApiResponse(data=plan)


@router.get("/plans", response_model=PaginatedResponse)
async def list_plans(
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    active_only: bool = Query(True),
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    items, total = await svc.list_plans(
        page=page, per_page=per_page, active_only=active_only
    )
    return PaginatedResponse(
        data=items,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
        },
    )


@router.get("/plans/{plan_id}", response_model=ApiResponse)
async def get_plan(
    plan_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    plan = await svc.get_plan(plan_id)
    return ApiResponse(data=plan)


@router.put("/plans/{plan_id}", response_model=ApiResponse)
async def update_plan(
    plan_id: UUID,
    body: ChittiPlanUpdate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    plan = await svc.update_plan(plan_id, data)
    return ApiResponse(data=plan)


@router.post("/plans/{plan_id}/duplicate", response_model=ApiResponse)
async def duplicate_plan(
    plan_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_CREATE),
):
    svc = ChittiService(db)
    plan = await svc.duplicate_plan(plan_id, created_by=current_user.id)
    return ApiResponse(data=plan)


@router.post("/plans/{plan_id}/deactivate", response_model=ApiResponse)
async def deactivate_plan(
    plan_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    plan = await svc.deactivate_plan(plan_id)
    return ApiResponse(data=plan)


@router.post("/plans/{plan_id}/activate", response_model=ApiResponse)
async def activate_plan(
    plan_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    plan = await svc.activate_plan(plan_id)
    return ApiResponse(data=plan)


@router.post("/plans/{plan_id}/preview", response_model=ApiResponse)
async def preview_plan(
    plan_id: UUID,
    body: ChittiPreviewRequest,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    preview = await svc.preview_chitti(
        plan_id=plan_id,
        start_date=body.start_date,
        member_count=body.member_count,
    )
    return ApiResponse(data=preview)


# ===========================================================================
# Chittis (Instances)
# ===========================================================================


@router.post("/", response_model=ApiResponse)
async def create_chitti(
    body: ChittiCreate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_CREATE),
):
    svc = ChittiService(db)
    chitti = await svc.create_chitti(
        data=body.model_dump(), created_by=current_user.id
    )
    return ApiResponse(data=chitti)


@router.get("/", response_model=PaginatedResponse)
async def list_chittis(
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str | None = Query(None),
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    items, total = await svc.list_chittis(
        page=page, per_page=per_page, status=status
    )
    return PaginatedResponse(
        data=items,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
        },
    )


@router.get("/dashboard", response_model=ApiResponse)
async def chitti_dashboard(
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    items = await svc.get_dashboard()
    return ApiResponse(data=items)


@router.get("/{chitti_id}", response_model=ApiResponse)
async def get_chitti(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    chitti = await svc.get_chitti(chitti_id)
    return ApiResponse(data=chitti)


@router.put("/{chitti_id}", response_model=ApiResponse)
async def update_chitti(
    chitti_id: UUID,
    body: ChittiUpdate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    chitti = await svc.update_chitti(chitti_id, data)
    return ApiResponse(data=chitti)


@router.get("/{chitti_id}/activation", response_model=ApiResponse)
async def chitti_activation(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    """Activation prerequisites: can this chitti start, and if not, why."""
    svc = ChittiService(db)
    return ApiResponse(data=await svc.evaluate_activation(chitti_id))


@router.post("/{chitti_id}/start", response_model=ApiResponse)
async def start_chitti(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    chitti = await svc.change_status(chitti_id, "RUNNING", created_by=current_user.id)
    return ApiResponse(data=chitti)


@router.post("/{chitti_id}/pause", response_model=ApiResponse)
async def pause_chitti(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    chitti = await svc.change_status(chitti_id, "PAUSED", created_by=current_user.id)
    return ApiResponse(data=chitti)


@router.post("/{chitti_id}/resume", response_model=ApiResponse)
async def resume_chitti(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    chitti = await svc.change_status(chitti_id, "RUNNING", created_by=current_user.id)
    return ApiResponse(data=chitti)


@router.post("/{chitti_id}/complete", response_model=ApiResponse)
async def complete_chitti(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    chitti = await svc.change_status(chitti_id, "COMPLETED", created_by=current_user.id)
    return ApiResponse(data=chitti)


@router.post("/{chitti_id}/cancel", response_model=ApiResponse)
async def cancel_chitti(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    chitti = await svc.change_status(chitti_id, "CANCELLED", created_by=current_user.id)
    return ApiResponse(data=chitti)


@router.get("/{chitti_id}/summary", response_model=ApiResponse)
async def chitti_summary(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    summary = await svc.get_summary(chitti_id)
    return ApiResponse(data=summary)


# ===========================================================================
# Members
# ===========================================================================


@router.post("/{chitti_id}/members", response_model=ApiResponse)
async def add_member(
    chitti_id: UUID,
    body: ChittiMemberAdd,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    from app.services.agreement_service import AgreementService
    svc = AgreementService(db)
    member = await svc.add_member(
        chitti_id,
        customer_id=body.customer_id,
        payout_order=body.payout_order,
        created_by=current_user.id,
    )
    return ApiResponse(data=member)


@router.get("/{chitti_id}/members", response_model=ApiResponse)
async def list_members(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    members = await svc.list_members(chitti_id)
    return ApiResponse(data=members)


@router.get("/{chitti_id}/members/{member_id}", response_model=ApiResponse)
async def get_member(
    chitti_id: UUID,
    member_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    member = await svc.get_member_detail(chitti_id, member_id)
    return ApiResponse(data=member)


@router.delete("/{chitti_id}/members/{member_id}", response_model=ApiResponse)
async def remove_member(
    chitti_id: UUID,
    member_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    await svc.remove_member(chitti_id, member_id)
    return ApiResponse(data={"message": "Member removed."})


# ===========================================================================
# Agreement Endpoints
# ===========================================================================


@router.post("/{chitti_id}/members/{member_id}/agreement/generate", response_model=ApiResponse)
async def generate_agreement(
    chitti_id: UUID,
    member_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    """Generate agreement for a PENDING_AGREEMENT member."""
    from app.services.agreement_service import AgreementService
    svc = AgreementService(db)
    agreement = await svc.generate_agreement(
        member_id, created_by=current_user.id
    )
    return ApiResponse(data=agreement)


@router.get("/{chitti_id}/members/{member_id}/agreement", response_model=ApiResponse)
async def get_agreement(
    chitti_id: UUID,
    member_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    """Get the agreement for a member."""
    from app.services.agreement_service import AgreementService
    svc = AgreementService(db)
    agreement = await svc.get_agreement_by_member(member_id)
    if not agreement:
        raise NotFoundException("Agreement", member_id)
    return ApiResponse(data=agreement)


@router.post("/{chitti_id}/members/{member_id}/agreement/print", response_model=ApiResponse)
async def print_agreement(
    chitti_id: UUID,
    member_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    """Record that the agreement was printed."""
    from app.services.agreement_service import AgreementService
    svc = AgreementService(db)
    agreement = await svc.get_agreement_by_member(member_id)
    if not agreement:
        raise NotFoundException("Agreement", member_id)
    from uuid import UUID as UUIDType
    result = await svc.print_agreement(UUIDType(agreement["id"]))
    return ApiResponse(data=result)


@router.post("/{chitti_id}/members/{member_id}/agreement/confirm", response_model=ApiResponse)
async def confirm_agreement(
    chitti_id: UUID,
    member_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    """Confirm agreement after physical signature. Activates the member."""
    from app.services.agreement_service import AgreementService
    svc = AgreementService(db)
    agreement = await svc.get_agreement_by_member(member_id)
    if not agreement:
        raise NotFoundException("Agreement", member_id)
    from uuid import UUID as UUIDType
    result = await svc.confirm_agreement(UUIDType(agreement["id"]))
    return ApiResponse(data=result)


@router.post("/{chitti_id}/members/{member_id}/cancel", response_model=ApiResponse)
async def cancel_member(
    chitti_id: UUID,
    member_id: UUID,
    body: MemberCancel,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    """Cancel a member enrollment."""
    from app.services.agreement_service import AgreementService
    svc = AgreementService(db)
    result = await svc.cancel_member(
        member_id, reason=body.reason or "", created_by=current_user.id
    )
    return ApiResponse(data=result)


# ===========================================================================
# Schedule & Contributions
# ===========================================================================


@router.get("/{chitti_id}/schedule", response_model=ApiResponse)
async def get_schedule(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    schedule = await svc.get_schedule(chitti_id)
    return ApiResponse(data=schedule)


@router.get("/{chitti_id}/members/{member_id}/contributions", response_model=ApiResponse)
async def get_member_contributions(
    chitti_id: UUID,
    member_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    contributions = await svc.get_member_contributions(chitti_id, member_id)
    return ApiResponse(data=contributions)


@router.post("/{chitti_id}/contributions", response_model=ApiResponse)
async def record_contribution(
    chitti_id: UUID,
    body: ChittiContributionPayment,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.PAYMENTS_CREATE),
):
    svc = ChittiService(db)
    result = await svc.record_contribution(
        chitti_id,
        member_id=body.member_id,
        period_number=body.period_number,
        amount=body.amount,
        payment_method=body.payment_method,
        payment_date=body.payment_date,
        reference_number=body.reference_number,
        notes=body.notes,
        idempotency_key=body.idempotency_key,
        created_by=current_user.id,
    )
    return ApiResponse(data=result)


# ===========================================================================
# Payouts
# ===========================================================================


@router.get("/{chitti_id}/payouts", response_model=ApiResponse)
async def list_payouts(
    chitti_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_READ),
):
    svc = ChittiService(db)
    payouts = await svc.list_payouts(chitti_id)
    return ApiResponse(data=payouts)


@router.post("/{chitti_id}/payouts", response_model=ApiResponse)
async def record_payout(
    chitti_id: UUID,
    body: ChittiPayoutRecord,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CHITTI_WRITE),
):
    svc = ChittiService(db)
    result = await svc.record_payout(
        chitti_id,
        member_id=body.member_id,
        period_number=body.period_number,
        gross_payout=body.gross_payout,
        discount_amount=body.discount_amount,
        fee_amount=body.fee_amount,
        net_payout=body.net_payout,
        payout_method=body.payout_method,
        created_by=current_user.id,
    )
    return ApiResponse(data=result)
