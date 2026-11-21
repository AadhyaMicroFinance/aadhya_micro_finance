"""
Finance Account and Finance Schedule models.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class FinanceAccount(BaseModel):
    """Finance loan account."""

    __tablename__ = "finance_accounts"

    account_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    principal_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    interest_type: Mapped[str] = mapped_column(
        Enum("FLAT", "REDUCING", name="interest_type_enum"),
        default="FLAT",
        nullable=False,
    )
    fees: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    total_payable: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    installment_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    custom_installment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    frequency: Mapped[str] = mapped_column(
        Enum("DAILY", "WEEKLY", "MONTHLY", name="frequency_enum"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    number_of_installments: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "ACTIVE", "COMPLETED", "DEFAULTED", "CLOSED",
            name="finance_status_enum",
        ),
        default="ACTIVE",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="finance_accounts")
    schedules: Mapped[list["FinanceSchedule"]] = relationship(
        "FinanceSchedule", back_populates="finance_account", cascade="all, delete-orphan"
    )
    payments: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction", back_populates="finance_account"
    )


class FinanceAgreement(BaseModel):
    """Finance loan agreement — immutable snapshot of the confirmed loan terms.

    This is deliberately a separate table and a separate enum from the Chitti
    agreement. Generation/printing alone never activates a Finance account: an
    agreement must be CONFIRMED before FinanceService can consume it.
    """

    __tablename__ = "finance_agreements"
    __table_args__ = (
        # One Finance account can only ever be backed by one agreement.
        UniqueConstraint("finance_account_id", name="uq_finance_agreement_account"),
    )

    agreement_number: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )

    # Separate enum name: Chitti's agreement status is untouched.
    agreement_status: Mapped[str] = mapped_column(
        Enum(
            "DRAFT", "GENERATED", "PRINTED", "CONFIRMED", "CANCELLED",
            name="finance_agreement_status_enum",
        ),
        default="GENERATED",
        nullable=False,
    )

    # Immutable snapshot of customer, loan terms and schedule at generation.
    agreement_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # SHA-256 over the canonical customer id + loan fields. The create endpoint
    # recomputes this independently, so edited terms cannot be smuggled in.
    terms_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    printed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    print_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Set exactly once, when the confirmed agreement is consumed by account
    # creation. Until then it is NULL, which keeps the agreement reusable for
    # neither a second account nor a modified set of terms.
    finance_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("finance_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )

    customer: Mapped["Customer"] = relationship("Customer")
    finance_account: Mapped["FinanceAccount | None"] = relationship("FinanceAccount")


class FinanceSchedule(BaseModel):
    """Individual installment schedule for a finance account."""

    __tablename__ = "finance_schedules"

    finance_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("finance_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    remaining_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "UPCOMING", "DUE", "PAID", "PARTIALLY_PAID", "OVERDUE", "CANCELLED",
            name="schedule_status_enum",
        ),
        default="UPCOMING",
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    finance_account: Mapped["FinanceAccount"] = relationship(
        "FinanceAccount", back_populates="schedules"
    )
    payments: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction", back_populates="finance_schedule"
    )
