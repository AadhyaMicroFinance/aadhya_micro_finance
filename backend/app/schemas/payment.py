"""
Payment schemas.
"""

from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class PaymentCreate(BaseModel):
    """Create a new payment."""

    customer_id: str
    finance_account_id: Optional[str] = None
    chitti_account_id: Optional[str] = None
    finance_schedule_id: Optional[str] = None
    chitti_schedule_id: Optional[str] = None
    amount: Decimal = Field(..., gt=0)
    payment_method: str = Field(..., pattern=r"^(CASH|UPI|BANK_TRANSFER|OTHER)$")
    payment_date: date = Field(default_factory=date.today)
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    idempotency_key: str = Field(..., min_length=1, max_length=100)


class PaymentReversalRequest(BaseModel):
    """Reverse an existing payment."""

    reversal_reason: str = Field(..., min_length=1, max_length=500)


class PaymentResponse(BaseModel):
    id: str
    transaction_id: str
    customer_id: str
    finance_account_id: Optional[str] = None
    chitti_account_id: Optional[str] = None
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
