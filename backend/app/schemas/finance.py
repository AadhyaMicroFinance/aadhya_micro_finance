"""
Finance schemas.
"""

from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class FinanceAccountCreate(BaseModel):
    customer_id: str
    principal_amount: Decimal = Field(..., gt=0)
    interest_rate: Decimal = Field(default=Decimal("0"), ge=0)
    interest_type: str = Field(default="FLAT", pattern=r"^(FLAT|REDUCING)$")
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    frequency: str = Field(..., pattern=r"^(DAILY|WEEKLY|MONTHLY)$")
    start_date: date
    first_due_date: date
    number_of_installments: int = Field(..., gt=0)
    custom_installment_amount: Optional[Decimal] = Field(None, gt=0)
    notes: Optional[str] = None


class FinanceAccountUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(ACTIVE|COMPLETED|DEFAULTED|CLOSED)$")
    notes: Optional[str] = None


class FinanceAccountResponse(BaseModel):
    id: str
    account_number: str
    customer_id: str
    principal_amount: Decimal
    interest_rate: Decimal
    interest_type: str
    fees: Decimal
    total_payable: Decimal
    installment_amount: Decimal
    frequency: str
    start_date: date
    first_due_date: date
    number_of_installments: int
    status: str
    notes: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class FinanceScheduleResponse(BaseModel):
    id: str
    installment_number: int
    due_date: date
    expected_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    status: str

    model_config = {"from_attributes": True}
