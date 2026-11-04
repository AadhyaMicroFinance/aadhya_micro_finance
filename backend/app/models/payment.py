"""
Payment Transaction model — immutable financial ledger.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class PaymentTransaction(BaseModel):
    """
    Immutable payment transaction record.
    Every payment creates a new row. No updates or deletes.
    Reversals create a new row with is_reversal=True pointing to the original.
    """

    __tablename__ = "payment_transactions"

    transaction_id: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    finance_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="SET NULL"), nullable=True
    )
    chitti_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chittis.id", ondelete="SET NULL"), nullable=True
    )
    finance_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_schedules.id", ondelete="SET NULL"), nullable=True
    )
    chitti_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chitti_period_schedule.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(
        Enum("CASH", "UPI", "BANK_TRANSFER", "OTHER", name="payment_method_enum"),
        nullable=False,
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_reversal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum("COMPLETED", "REVERSED", "PENDING", name="payment_status_enum"),
        default="COMPLETED",
        nullable=False,
    )

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="payments")
    finance_account: Mapped["FinanceAccount | None"] = relationship(
        "FinanceAccount", back_populates="payments"
    )
    chitti_group: Mapped["Chitti | None"] = relationship(
        "Chitti"
    )
    finance_schedule: Mapped["FinanceSchedule | None"] = relationship(
        "FinanceSchedule", back_populates="payments"
    )
    chitti_schedule: Mapped["ChittiPeriodSchedule | None"] = relationship(
        "ChittiPeriodSchedule"
    )
    collector: Mapped["User | None"] = relationship("User")
