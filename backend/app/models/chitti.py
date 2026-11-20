"""
Chitti models — flexible, rule-based architecture.

Separates:
  ChittiPlan     → Reusable template with configurable rules (JSONB)
  Chitti         → A running instance created from a plan (with plan snapshot)
  ChittiMember   → Members assigned to a running chitti
  ChittiPeriodSchedule       → Generated period-level schedule
  ChittiMemberContribution   → Per-member per-period contribution tracking
  ChittiPayout                → Per-member payout records
  ChittiTransaction           → Immutable financial ledger
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


# ---------------------------------------------------------------------------
# Chitti Plan
# ---------------------------------------------------------------------------

class ChittiPlan(BaseModel):
    """Reusable plan template with configurable rules."""

    __tablename__ = "chitti_plans"

    plan_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Type: FIXED, VARIABLE, AUCTION, CUSTOM
    chitti_type: Mapped[str] = mapped_column(
        Enum(
            "FIXED", "VARIABLE", "AUCTION", "CUSTOM", "LIFT_BASED",
            name="chitti_plan_type_enum",
        ),
        nullable=False,
    )

    total_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Frequency: DAILY, WEEKLY, BIWEEKLY, MONTHLY, CUSTOM
    frequency: Mapped[str] = mapped_column(
        Enum(
            "DAILY", "WEEKLY", "BIWEEKLY", "MONTHLY", "CUSTOM",
            name="chitti_frequency_enum",
        ),
        nullable=False,
    )
    duration: Mapped[int] = mapped_column(Integer, nullable=False)

    # ---- Flexible rule storage (JSONB) ----
    # Contribution rules: installment amounts, schedules, advance, partial
    contribution_rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Payout rules: scheduled, auction, custom order
    payout_rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Fee rules: registration, management, etc.
    fee_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    # Penalty rules: grace period, late fees
    penalty_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    chittis: Mapped[list["Chitti"]] = relationship(
        "Chitti", back_populates="plan", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Chitti (running instance)
# ---------------------------------------------------------------------------

class Chitti(BaseModel):
    """A running chitti instance created from a plan.
    
    plan_snapshot is a JSONB copy of the plan rules at creation time.
    This ensures that modifying the plan later does NOT affect running chittis.
    """

    __tablename__ = "chittis"

    chitti_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chitti_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Immutable snapshot of plan rules at creation time
    plan_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(100), nullable=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    current_period: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Status: DRAFT, UPCOMING, RUNNING, PAUSED, COMPLETED, CANCELLED, ARCHIVED
    status: Mapped[str] = mapped_column(
        Enum(
            "DRAFT", "UPCOMING", "RUNNING", "PAUSED",
            "COMPLETED", "CANCELLED", "ARCHIVED",
            name="chitti_status_enum",
        ),
        default="DRAFT",
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    plan: Mapped["ChittiPlan"] = relationship("ChittiPlan", back_populates="chittis")
    members: Mapped[list["ChittiMember"]] = relationship(
        "ChittiMember", back_populates="chitti", cascade="all, delete-orphan"
    )
    period_schedule: Mapped[list["ChittiPeriodSchedule"]] = relationship(
        "ChittiPeriodSchedule", back_populates="chitti", cascade="all, delete-orphan"
    )
    contributions: Mapped[list["ChittiMemberContribution"]] = relationship(
        "ChittiMemberContribution", back_populates="chitti", cascade="all, delete-orphan"
    )
    payouts: Mapped[list["ChittiPayout"]] = relationship(
        "ChittiPayout", back_populates="chitti", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["ChittiTransaction"]] = relationship(
        "ChittiTransaction", back_populates="chitti", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Chitti Member
# ---------------------------------------------------------------------------

class ChittiMember(BaseModel):
    """Individual member within a running chitti."""

    __tablename__ = "chitti_members"
    __table_args__ = (
        UniqueConstraint("chitti_id", "member_number", name="uq_chitti_member_number"),
        Index(
            "uq_chitti_member_alias",
            "chitti_id",
            "alias",
            unique=True,
            postgresql_where=text("alias IS NOT NULL"),
        ),
    )

    chitti_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chittis.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    member_number: Mapped[int] = mapped_column(Integer, nullable=False)
    payout_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Enrollment status: PENDING_AGREEMENT → AGREEMENT_GENERATED → AGREEMENT_PRINTED → ACTIVE
    status: Mapped[str] = mapped_column(
        Enum(
            "PENDING_AGREEMENT", "AGREEMENT_GENERATED", "AGREEMENT_PRINTED",
            "ACTIVE", "REJECTED", "CANCELLED", "COMPLETED",
            "LEFT", "REPLACED",
            name="chitti_member_status_enum",
        ),
        default="PENDING_AGREEMENT",
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Agreement tracking
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chitti_agreements.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Financial tracking
    total_expected_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    total_paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    outstanding_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )

    # Lifting tracking
    lifted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lifted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lift_period: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    chitti: Mapped["Chitti"] = relationship("Chitti", back_populates="members")
    customer = relationship("Customer")
    contributions: Mapped[list["ChittiMemberContribution"]] = relationship(
        "ChittiMemberContribution", back_populates="member"
    )
    payouts: Mapped[list["ChittiPayout"]] = relationship(
        "ChittiPayout", back_populates="member"
    )


# ---------------------------------------------------------------------------
# Lift Event (separate from payout transactions)
# ---------------------------------------------------------------------------

class ChittiLiftEvent(BaseModel):
    """Confirmed member lift for a contribution period; not proof of payout."""

    __tablename__ = "chitti_lift_events"
    __table_args__ = (
        Index("uq_chitti_lift_period_active", "chitti_id", "period_number",
              unique=True, postgresql_where=text("reversed_at IS NULL")),
    )

    chitti_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chittis.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chitti_members.id", ondelete="RESTRICT"), nullable=False
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lift_date: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Period Schedule
# ---------------------------------------------------------------------------

class ChittiPeriodSchedule(BaseModel):
    """Period-level schedule for a running chitti.
    
    One row per period (e.g., week 1, week 2, ...).
    Tracks aggregate collection and payout for that period.
    """

    __tablename__ = "chitti_period_schedule"
    __table_args__ = (
        UniqueConstraint("chitti_id", "period_number", name="uq_chitti_period"),
        CheckConstraint("expected_collection >= 0", name="ck_chitti_period_expected_collection_nonnegative"),
        CheckConstraint("actual_collection >= 0", name="ck_chitti_period_actual_collection_nonnegative"),
        CheckConstraint("pending_collection >= 0", name="ck_chitti_period_pending_collection_nonnegative"),
        CheckConstraint("expected_payout >= 0", name="ck_chitti_period_expected_payout_nonnegative"),
        CheckConstraint("actual_payout >= 0", name="ck_chitti_period_actual_payout_nonnegative"),
    )

    chitti_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chittis.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    expected_collection: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    actual_collection: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    pending_collection: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    expected_payout: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    actual_payout: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "UPCOMING", "ACTIVE", "COMPLETED", "OVERDUE",
            name="chitti_period_status_enum",
        ),
        default="UPCOMING",
        nullable=False,
    )

    # Relationships
    chitti: Mapped["Chitti"] = relationship("Chitti", back_populates="period_schedule")


# ---------------------------------------------------------------------------
# Member Contribution (per period)
# ---------------------------------------------------------------------------

class ChittiMemberContribution(BaseModel):
    """Per-member per-period contribution tracking."""

    __tablename__ = "chitti_member_contributions"
    __table_args__ = (
        UniqueConstraint(
            "chitti_id", "member_id", "period_number",
            name="uq_chitti_member_period",
        ),
        CheckConstraint("expected_amount >= 0", name="ck_chitti_contribution_expected_amount_nonnegative"),
        CheckConstraint("paid_amount >= 0", name="ck_chitti_contribution_paid_amount_nonnegative"),
        CheckConstraint("remaining_amount >= 0", name="ck_chitti_contribution_remaining_amount_nonnegative"),
    )

    chitti_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chittis.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chitti_members.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)

    expected_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    remaining_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "UPCOMING", "PAID", "PARTIALLY_PAID", "OVERDUE", "WAIVED",
            name="chitti_contribution_status_enum",
        ),
        default="UPCOMING",
        nullable=False,
    )

    # Relationships
    chitti: Mapped["Chitti"] = relationship("Chitti", back_populates="contributions")
    member: Mapped["ChittiMember"] = relationship(
        "ChittiMember", back_populates="contributions"
    )


# ---------------------------------------------------------------------------
# Payout
# ---------------------------------------------------------------------------

class ChittiPayout(BaseModel):
    """Payout record per member per period."""

    __tablename__ = "chitti_payouts"
    __table_args__ = (
        UniqueConstraint(
            "ledger_transaction_id",
            name="uq_chitti_payout_ledger_transaction",
        ),
        UniqueConstraint(
            "chitti_id", "member_id", "period_number",
            name="uq_chitti_payout_member_period",
        ),
        CheckConstraint("gross_payout >= 0", name="ck_chitti_payout_gross_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="ck_chitti_payout_discount_nonnegative"),
        CheckConstraint("fee_amount >= 0", name="ck_chitti_payout_fee_nonnegative"),
        CheckConstraint("net_payout >= 0", name="ck_chitti_payout_net_nonnegative"),
        CheckConstraint(
            "net_payout = gross_payout - discount_amount - fee_amount",
            name="ck_chitti_payout_net_arithmetic",
        ),
    )

    chitti_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chittis.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chitti_members.id", ondelete="CASCADE"),
        nullable=False,
    )
    ledger_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chitti_transactions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)

    gross_payout: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    net_payout: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    payout_method: Mapped[str | None] = mapped_column(
        Enum("CASH", "UPI", "BANK_TRANSFER", "OTHER", name="payout_method_enum"),
        nullable=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(
        Enum("PENDING", "PAID", "CANCELLED", name="chitti_payout_status_enum"),
        default="PENDING",
        nullable=False,
    )

    # Relationships
    chitti: Mapped["Chitti"] = relationship("Chitti", back_populates="payouts")
    member: Mapped["ChittiMember"] = relationship(
        "ChittiMember", back_populates="payouts"
    )
    ledger_transaction: Mapped["ChittiTransaction | None"] = relationship(
        "ChittiTransaction",
        foreign_keys=[ledger_transaction_id],
        viewonly=True,
    )


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------

class ChittiAgreement(BaseModel):
    """Chitti enrollment agreement — snapshot of terms at enrollment time."""

    __tablename__ = "chitti_agreements"

    agreement_number: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )
    chitti_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chittis.id", ondelete="CASCADE"),
        nullable=False,
    )
    chitti_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chitti_members.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )

    agreement_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Status: DRAFT → GENERATED → PRINTED → CONFIRMED → CANCELLED
    agreement_status: Mapped[str] = mapped_column(
        Enum(
            "DRAFT", "GENERATED", "PRINTED", "CONFIRMED", "CANCELLED",
            name="agreement_status_enum",
        ),
        default="DRAFT",
        nullable=False,
    )

    # Immutable snapshot of all terms at agreement time
    agreement_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Tracking
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
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    chitti = relationship("Chitti")
    chitti_member = relationship("ChittiMember", foreign_keys=[chitti_member_id])
    customer = relationship("Customer")


# ---------------------------------------------------------------------------
# Transaction Ledger (immutable)
# ---------------------------------------------------------------------------

class ChittiTransaction(BaseModel):
    """Immutable financial ledger for all chitti money movement."""

    __tablename__ = "chitti_transactions"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_chitti_transaction_amount_nonnegative"),
        UniqueConstraint(
            "original_transaction_id",
            name="uq_chitti_transaction_original",
        ),
    )

    chitti_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chittis.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(
        Enum(
            "CONTRIBUTION", "PAYOUT", "PENALTY", "FEE", "REVERSAL",
            name="chitti_transaction_type_enum",
        ),
        nullable=False,
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chitti_members.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chitti_transactions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(
        Enum("CASH", "UPI", "BANK_TRANSFER", "OTHER", name="chitti_txn_payment_method_enum"),
        nullable=True,
    )
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    period_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Business date the money was actually received (may differ from insertion time
    # for back-dated cash entries) — analytics bucket on this, not created_at.
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Optional client-supplied key so a retried request cannot double-count money.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    chitti: Mapped["Chitti"] = relationship("Chitti", back_populates="transactions")
    original_transaction: Mapped["ChittiTransaction | None"] = relationship(
        "ChittiTransaction",
        remote_side="ChittiTransaction.id",
        foreign_keys=[original_transaction_id],
        viewonly=True,
    )


class ChittiPaymentAllocation(BaseModel):
    """Append-only allocation movements for a contribution receipt or credit."""

    __tablename__ = "chitti_payment_allocations"
    __table_args__ = (
        CheckConstraint(
            "amount <> 0",
            name="ck_chitti_payment_allocation_amount_nonzero",
        ),
        CheckConstraint(
            "(allocation_type = 'CREDIT' AND contribution_id IS NULL) OR "
            "(allocation_type = 'CONTRIBUTION' AND contribution_id IS NOT NULL)",
            name="ck_chitti_payment_allocation_target",
        ),
        Index(
            "ix_chitti_payment_allocations_source_transaction",
            "source_transaction_id",
        ),
        Index(
            "ix_chitti_payment_allocations_member",
            "chitti_id",
            "member_id",
        ),
        Index(
            "ix_chitti_payment_allocations_contribution",
            "contribution_id",
        ),
    )

    chitti_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chittis.id",
            name="fk_chitti_payment_allocations_chitti_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chitti_members.id",
            name="fk_chitti_payment_allocations_member_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chitti_transactions.id",
            name="fk_chitti_payment_allocations_source_transaction_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    event_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chitti_transactions.id",
            name="fk_chitti_payment_allocations_event_transaction_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    contribution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chitti_member_contributions.id",
            name="fk_chitti_payment_allocations_contribution_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    allocation_type: Mapped[str] = mapped_column(
        Enum("CONTRIBUTION", "CREDIT", name="chitti_payment_allocation_type_enum"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        Enum(
            "PAYMENT", "REVERSAL", "CREDIT_UTILIZATION", "LIFT_ADJUSTMENT",
            name="chitti_payment_allocation_event_type_enum",
        ),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
