"""
Payment schemas.
"""

from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from datetime import date


class PaymentCreate(BaseModel):
    """Create a Finance repayment. Chitti contributions use their own endpoint."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str
    finance_account_id: str
    finance_schedule_id: str
    amount: Decimal = Field(..., gt=0)
    payment_method: str = Field(..., pattern=r"^(CASH|UPI|BANK_TRANSFER|OTHER)$")
    payment_date: date = Field(default_factory=date.today)
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    idempotency_key: str = Field(..., min_length=1, max_length=100)

    @field_validator(
        "customer_id",
        "finance_account_id",
        "finance_schedule_id",
        mode="before",
    )
    @classmethod
    def validate_id_format(cls, value):
        """Reject malformed IDs here (422) instead of letting uuid.UUID()
        raise deep in the service and surface as an opaque 500."""
        if value is not None:
            UUID(str(value))
        return value


class PaymentReversalRequest(BaseModel):
    """Reverse an existing payment."""

    reversal_reason: str = Field(..., min_length=1, max_length=500)


class PaymentResponse(BaseModel):
    id: str
    transaction_id: str
    customer_id: str
    finance_account_id: Optional[str] = None
    amount: Decimal
    payment_method: str
    payment_date: date
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    is_reversal: bool
    status: str
    collected_by: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


class DueInfo(BaseModel):
    """Information about amount due for an account."""

    account_id: str
    account_number: str
    account_type: str  # FINANCE or CHITTI
    amount_due: Decimal
    outstanding: Decimal
    next_due_date: Optional[date] = None
    next_installment_number: Optional[int] = None
    total_paid: Decimal
    total_payable: Decimal
