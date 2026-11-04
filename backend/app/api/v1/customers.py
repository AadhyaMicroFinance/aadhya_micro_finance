"""
Customer management API endpoints — full onboarding fields.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.permissions import Permission, require_permissions
from app.dependencies import CurrentUser, DBSession
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.customer_service import CustomerService

router = APIRouter()


@router.post("/", response_model=ApiResponse)
async def create_customer(
    body: CustomerCreate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CUSTOMERS_WRITE),
):
    """Register a new customer (onboarding)."""
    service = CustomerService(db)
    customer = await service.create_customer(**body.model_dump())
    return ApiResponse(data=customer)


@router.get("/", response_model=PaginatedResponse)
async def list_customers(
    db: DBSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: CurrentUser = require_permissions(Permission.CUSTOMERS_READ),
):
    service = CustomerService(db)
    items, total = await service.list_customers(
        page=page, per_page=per_page, status=status, search=search
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


@router.get("/{customer_id}", response_model=ApiResponse)
async def get_customer(
    customer_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CUSTOMERS_READ),
):
    service = CustomerService(db)
    customer = await service.get_customer(customer_id)
    return ApiResponse(data=customer)


@router.put("/{customer_id}", response_model=ApiResponse)
async def update_customer(
    customer_id: UUID,
    body: CustomerUpdate,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CUSTOMERS_WRITE),
):
    service = CustomerService(db)
    customer = await service.update_customer(
        customer_id, **body.model_dump(exclude_unset=True)
    )
    return ApiResponse(data=customer)


@router.get("/{customer_id}/ledger", response_model=ApiResponse)
async def get_customer_ledger(
    customer_id: UUID,
    db: DBSession,
    current_user: CurrentUser = require_permissions(Permission.CUSTOMERS_READ),
):
    service = CustomerService(db)
    ledger = await service.get_customer_ledger(customer_id)
    return ApiResponse(data=ledger)
