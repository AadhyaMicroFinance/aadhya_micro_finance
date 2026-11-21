"""
Finance account, agreement, dashboard and collection API endpoints.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.permissions import Permission, require_permissions
from app.dependencies import DBSession
from app.models.user import User
from app.schemas.finance import (
    FinanceAccountCreate,
    FinanceAccountUpdate,
    FinanceAccountResponse,
    FinanceAgreementConfirm,
    FinanceAgreementGenerate,
    FinanceScheduleResponse,
)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.finance_agreement_service import FinanceAgreementService
from app.services.finance_dashboard_service import FinanceDashboardService
from app.services.finance_service import FinanceService
from app.services.payment_service import PaymentService

router = APIRouter()


# ---------------------------------------------------------------------------
# Agreement workflow (declared before /{account_id} so static paths win)
# ---------------------------------------------------------------------------


@router.post("/agreements/generate", response_model=ApiResponse)
async def generate_finance_agreement(
    body: FinanceAgreementGenerate,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_CREATE)),
):
    """Generate a Finance loan agreement snapshot; no account is created."""
    service = FinanceAgreementService(db)
    agreement = await service.generate_agreement(
        body.model_dump(), created_by=current_user.id
    )
    return ApiResponse(data=agreement)


@router.get("/agreements/{agreement_id}", response_model=ApiResponse)
async def review_finance_agreement(
    agreement_id: UUID,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_READ)),
):
    """Review a generated, printed or confirmed Finance agreement."""
    service = FinanceAgreementService(db)
    return ApiResponse(data=await service.get_agreement(agreement_id))


@router.post("/agreements/{agreement_id}/print", response_model=ApiResponse)
async def print_finance_agreement(
    agreement_id: UUID,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_CREATE)),
):
    """Record a print run; a printed agreement is still not confirmed."""
    service = FinanceAgreementService(db)
    return ApiResponse(
        data=await service.print_agreement(agreement_id, created_by=current_user.id)
    )


@router.get("/agreements/{agreement_id}/download")
async def download_finance_agreement(
    agreement_id: UUID,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_READ)),
):
    """Download the agreement as an attached HTML document (read-only)."""
    service = FinanceAgreementService(db)
    document = await service.download_agreement(agreement_id)
    return Response(
        content=document["content"],
        media_type=document["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{document["filename"]}"'
        },
    )


@router.post("/agreements/{agreement_id}/confirm", response_model=ApiResponse)
async def confirm_finance_agreement(
    agreement_id: UUID,
    body: FinanceAgreementConfirm,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_CREATE)),
):
    """Confirm the signed agreement with the exact confirmation text."""
    service = FinanceAgreementService(db)
    return ApiResponse(
        data=await service.confirm_agreement(
            agreement_id,
            confirmation_text=body.confirmation_text,
            confirmed_by=current_user.id,
        )
    )


# ---------------------------------------------------------------------------
# Finance-only dashboard and collections
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=ApiResponse)
async def get_finance_dashboard(
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_READ)),
):
    """Finance-only KPIs, trends and repayment queues."""
    service = FinanceDashboardService(db)
    return ApiResponse(data=await service.get_dashboard())


@router.get("/collections", response_model=PaginatedResponse)
async def list_finance_collections(
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    customer_id: Optional[UUID] = None,
    finance_account_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_permissions(Permission.FINANCE_READ)),
):
    """Paginated Finance-only payment history (never Chitti ledger rows)."""
    service = PaymentService(db)
    items, total = await service.list_payment_history(
        page=page,
        per_page=per_page,
        customer_id=customer_id,
        finance_account_id=finance_account_id,
        finance_only=True,
        date_from=date_from,
        date_to=date_to,
        search=search,
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


@router.get("/collections/pending", response_model=ApiResponse)
async def list_finance_pending_collections(
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_READ)),
):
    """Finance-only due/overdue installments."""
    service = PaymentService(db)
    records = await service.list_pending_collections(finance_only=True)
    return ApiResponse(data=records)


# ---------------------------------------------------------------------------
# Finance accounts
# ---------------------------------------------------------------------------


@router.post("/", response_model=ApiResponse)
async def create_finance_account(
    body: FinanceAccountCreate,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_CREATE)),
):
    """Create a Finance account from a confirmed agreement."""
    service = FinanceService(db)
    account = await service.create_account(
        agreement_id=body.agreement_id,
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
    customer_id: Optional[UUID] = None,
    search: Optional[str] = None,
    agreement_status: Optional[str] = None,
    current_user: User = Depends(require_permissions(Permission.FINANCE_READ)),
):
    """List finance accounts with pagination, search and agreement status."""
    service = FinanceService(db)
    items, total = await service.list_accounts(
        page=page,
        per_page=per_page,
        status=status,
        customer_id=customer_id,
        search=search,
        agreement_status=agreement_status,
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
    current_user: User = Depends(require_permissions(Permission.FINANCE_READ)),
):
    """Get a finance account by ID."""
    service = FinanceService(db)
    account = await service.get_account(account_id)
    return ApiResponse(data=account)


@router.get("/{account_id}/schedule", response_model=ApiResponse)
async def get_finance_schedule(
    account_id: UUID,
    db: DBSession,
    current_user: User = Depends(require_permissions(Permission.FINANCE_READ)),
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
    current_user: User = Depends(require_permissions(Permission.FINANCE_WRITE)),
):
    """Update editable finance-account metadata (status and notes)."""
    service = FinanceService(db)
    account = await service.update_account(
        account_id,
        **body.model_dump(exclude_unset=True),
        updated_by=current_user.id,
    )
    return ApiResponse(data=account)
