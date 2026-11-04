"""
Finance Account and Finance Schedule models.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
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
