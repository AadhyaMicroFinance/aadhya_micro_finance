"""
Finance schemas.
"""

from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date


class FinanceLoanTerms(BaseModel):
    """Loan fields shared by agreement generation and account creation."""

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

    @field_validator("customer_id", mode="before")
    @classmethod
    def validate_customer_id_format(cls, value):
        """Reject malformed IDs here (422) instead of as an opaque 500."""
        UUID(str(value))
        return value


class FinanceAgreementGenerate(FinanceLoanTerms):
    """Body for POST /finance/agreements/generate (loan fields only)."""


class FinanceAgreementConfirm(BaseModel):
    confirmation_text: str


class FinanceAccountCreate(FinanceLoanTerms):
    """Finance account creation requires a confirmed agreement."""

    agreement_id: str

    @field_validator("agreement_id", mode="before")
    @classmethod
    def validate_agreement_id_format(cls, value):
        UUID(str(value))
        return value


class FinanceAccountUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(ACTIVE|COMPLETED|DEFAULTED|CLOSED)$")
    notes: Optional[str] = None


class FinanceAccountResponse(BaseModel):
    id: str
    account_number: str
    customer_id: str
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    mobile_number: Optional[str] = None
    agreement_status: str = "NONE"
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
