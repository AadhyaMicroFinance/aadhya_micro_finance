"""
Chitti schemas — Plan, Instance, Members, Schedule, Contributions, Payouts.
"""

from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import date, datetime


# ===========================================================================
# Plan Schemas
# ===========================================================================


class ChittiPlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    chitti_type: str = Field(..., pattern=r"^(FIXED|VARIABLE|AUCTION|CUSTOM|LIFT_BASED)$")
    total_value: Decimal = Field(..., gt=0)
    currency: str = Field(default="INR", max_length=3)
    member_count: int = Field(..., gt=0)
    frequency: str = Field(..., pattern=r"^(DAILY|WEEKLY|BIWEEKLY|MONTHLY|CUSTOM)$")
    duration: int = Field(..., gt=0)
    contribution_rules: dict = Field(..., description="Flexible contribution rules as JSON")
    payout_rules: dict = Field(..., description="Payout rules as JSON")
    fee_rules: Optional[dict] = Field(default_factory=dict)
    penalty_rules: Optional[dict] = Field(default_factory=dict)


class ChittiPlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    total_value: Optional[Decimal] = Field(None, gt=0)
    member_count: Optional[int] = Field(None, gt=0)
    frequency: Optional[str] = Field(None, pattern=r"^(DAILY|WEEKLY|BIWEEKLY|MONTHLY|CUSTOM)$")
    duration: Optional[int] = Field(None, gt=0)
    contribution_rules: Optional[dict] = None
    payout_rules: Optional[dict] = None
    fee_rules: Optional[dict] = None
    penalty_rules: Optional[dict] = None
    is_active: Optional[bool] = None


class ChittiPlanResponse(BaseModel):
    id: str
    plan_code: str
    name: str
    description: Optional[str] = None
    chitti_type: str
    total_value: Decimal
    currency: str
    member_count: int
    frequency: str
    duration: int
    contribution_rules: dict
    payout_rules: dict
    fee_rules: Optional[dict] = None
    penalty_rules: Optional[dict] = None
    is_active: bool
    created_by: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ===========================================================================
# Chitti (Instance) Schemas
# ===========================================================================


class ChittiCreate(BaseModel):
    """Create a chitti instance from an existing plan."""
    plan_id: str
    name: str = Field(..., min_length=1, max_length=255)
    branch: Optional[str] = Field(None, max_length=100)
    start_date: date
    member_count: Optional[int] = Field(None, gt=0, description="Override plan member_count if allowed")
    notes: Optional[str] = None


class ChittiUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    branch: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class ChittiResponse(BaseModel):
    id: str
    chitti_code: str
    plan_id: str
    plan_name: Optional[str] = None
    name: str
    branch: Optional[str] = None
    start_date: str
    end_date: str
    member_count: int
    total_value: Decimal
    current_period: int
    status: str
    notes: Optional[str] = None
    plan_snapshot: Optional[dict] = None
    created_by: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ChittiListResponse(BaseModel):
    id: str
    chitti_code: str
    plan_id: str
    plan_name: Optional[str] = None
    name: str
    branch: Optional[str] = None
    start_date: str
    end_date: str
    member_count: int
    total_value: Decimal
    current_period: int
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class ChittiDashboardItem(BaseModel):
    """Compact summary for running chittis dashboard."""
    id: str
    chitti_code: str
    name: str
    plan_name: Optional[str] = None
    status: str
    member_count: int
    current_period: int
    total_periods: int
    total_value: Decimal
    expected_collection: Decimal
    actual_collection: Decimal
    pending_collection: Decimal
    next_due_date: Optional[str] = None
    start_date: str
    end_date: str


# ===========================================================================
# Member Schemas
# ===========================================================================


class ChittiMemberAdd(BaseModel):
    customer_id: str
    payout_order: Optional[int] = Field(None, ge=0)


class ChittiMemberResponse(BaseModel):
    id: str
    chitti_id: str
    customer_id: str
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    mobile_number: Optional[str] = None
    member_number: int
    payout_order: Optional[int] = None
    status: str
    joined_at: str
    total_expected: Decimal = Decimal("0")
    total_paid: Decimal = Decimal("0")
    outstanding: Decimal = Decimal("0")

    model_config = {"from_attributes": True}


# ===========================================================================
# Schedule Schemas
# ===========================================================================


class ChittiPeriodScheduleResponse(BaseModel):
    id: str
    chitti_id: str
    period_number: int
    due_date: str
    expected_collection: Decimal
    actual_collection: Decimal
    pending_collection: Decimal
    expected_payout: Decimal
    actual_payout: Decimal
    status: str

    model_config = {"from_attributes": True}


class ChittiMemberContributionResponse(BaseModel):
    id: str
    member_id: str
    customer_name: Optional[str] = None
    period_number: int
    expected_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    status: str

    model_config = {"from_attributes": True}


# ===========================================================================
# Payout Schemas
# ===========================================================================


class ChittiPayoutRecord(BaseModel):
    """Record a payout for a period."""
    member_id: str
    period_number: int
    gross_payout: Decimal = Field(..., ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    fee_amount: Decimal = Field(default=Decimal("0"), ge=0)
    net_payout: Decimal = Field(..., ge=0)
    payout_method: str = Field(..., pattern=r"^(CASH|UPI|BANK_TRANSFER|OTHER)$")


class ChittiPayoutResponse(BaseModel):
    id: str
    chitti_id: str
    member_id: str
    customer_name: Optional[str] = None
    period_number: int
    gross_payout: Decimal
    discount_amount: Decimal
    fee_amount: Decimal
    net_payout: Decimal
    payout_method: Optional[str] = None
    paid_at: Optional[str] = None
    status: str

    model_config = {"from_attributes": True}


# ===========================================================================
# Contribution Payment
# ===========================================================================


class ChittiContributionPayment(BaseModel):
    """Record a contribution payment for a member."""
    member_id: str
    period_number: int
    amount: Decimal = Field(..., gt=0)
    payment_method: str = Field(..., pattern=r"^(CASH|UPI|BANK_TRANSFER|OTHER)$")
    payment_date: date = Field(default_factory=date.today)
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    idempotency_key: str = Field(..., min_length=1, max_length=100)


# ===========================================================================
# Preview / Simulation
# ===========================================================================


class ChittiPreviewRequest(BaseModel):
    """Preview a chitti before creation."""
    plan_id: str
    start_date: date
    member_count: Optional[int] = Field(None, gt=0)


class ChittiPeriodPreview(BaseModel):
    period_number: int
    due_date: str
    expected_collection: Decimal
    expected_payout: Decimal
    status: str


class ChittiMemberInstallmentPreview(BaseModel):
    period: int
    due_date: Optional[str] = None
    amount: Decimal


class ChittiPreviewResponse(BaseModel):
    periods: list[ChittiPeriodPreview]
    total_expected_collection: Decimal
    total_expected_payout: Decimal
    per_member_installment_schedule: list[ChittiMemberInstallmentPreview]
    plan_name: str
    chitti_type: str
    frequency: str
    duration: int
    member_count: int
    total_value: Decimal


# ===========================================================================
# Summary
# ===========================================================================


class ChittiSummaryResponse(BaseModel):
    """Financial summary for a chitti."""
    chitti_id: str
    chitti_name: str
    status: str
    member_count: int
    active_members: int
    current_period: int
    total_periods: int
    total_value: Decimal
    expected_collection: Decimal
    actual_collection: Decimal
    pending_collection: Decimal
    total_payouts: Decimal
    outstanding: Decimal
    next_due_date: Optional[str] = None
    next_payout_date: Optional[str] = None


# ===========================================================================
# Agreement Schemas
# ===========================================================================


class AgreementGenerate(BaseModel):
    """Request to generate agreement for a member."""
    pass  # No additional data needed — uses member + chitti data


class AgreementResponse(BaseModel):
    id: str
    agreement_number: str
    chitti_id: str
    chitti_member_id: str
    customer_id: str
    agreement_date: str
    agreement_status: str
    agreement_snapshot: dict
    generated_at: Optional[str] = None
    printed_at: Optional[str] = None
    print_count: int
    confirmed_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AgreementConfirm(BaseModel):
    """Confirm agreement after physical signature."""
    pass  # No additional data needed


class MemberCancel(BaseModel):
    """Cancel a member enrollment."""
    reason: Optional[str] = None


class ChittiMemberDetail(BaseModel):
    """Full member detail with agreement info."""
    id: str
    chitti_id: str
    customer_id: str
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    mobile_number: Optional[str] = None
    member_number: int
    payout_order: Optional[int] = None
    status: str
    joined_at: str
    total_expected_amount: Decimal = Decimal("0")
    total_paid_amount: Decimal = Decimal("0")
    outstanding_amount: Decimal = Decimal("0")
    lifted: bool = False
    lifted_at: Optional[str] = None
    lift_period: Optional[int] = None
    agreement: Optional[AgreementResponse] = None

    model_config = {"from_attributes": True}
