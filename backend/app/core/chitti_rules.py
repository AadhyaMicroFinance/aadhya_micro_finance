"""
Chitti Rule Definitions — Pydantic models for validating JSONB rule storage.

Each rule type is a Pydantic model that:
1. Validates the rule structure on plan creation/update
2. Documents the contract for frontend dynamic forms
3. Is used by calculation strategies to compute schedules
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ===========================================================================
# Contribution Rules
# ===========================================================================


class FixedContributionRule(BaseModel):
    """Fixed installment amount for every period."""

    type: str = "FIXED"
    installment_amount: Decimal = Field(..., gt=0)
    advance_payment: Optional[Decimal] = Field(None, ge=0)
    first_installment_different: bool = False
    first_installment_amount: Optional[Decimal] = Field(None, gt=0)
    last_installment_different: bool = False
    last_installment_amount: Optional[Decimal] = Field(None, gt=0)
    partial_payments_allowed: bool = True


class ScheduleEntry(BaseModel):
    period: int = Field(..., ge=1)
    amount: Decimal = Field(..., gt=0)


class VariableContributionRule(BaseModel):
    """Variable installment — explicit schedule per period."""

    type: str = "SCHEDULE"
    schedule: list[ScheduleEntry] = Field(..., min_length=1)
    repeat_last_for_remaining: bool = True

    @model_validator(mode="after")
    def validate_schedule(self):
        amounts = [e.amount for e in self.schedule]
        if any(a <= 0 for a in amounts):
            raise ValueError("All scheduled amounts must be positive")
        return self


class PercentageContributionRule(BaseModel):
    """Installment as a percentage of total value."""

    type: str = "PERCENTAGE"
    percentage_of_total: Decimal = Field(..., gt=0, le=100)
    min_amount: Optional[Decimal] = Field(None, ge=0)
    max_amount: Optional[Decimal] = Field(None, gt=0)


class CustomScheduleEntry(BaseModel):
    period: int = Field(..., ge=1)
    amount: Decimal = Field(..., gt=0)


class CustomContributionRule(BaseModel):
    """Custom installment — admin manually defines amount for each period."""

    type: str = "CUSTOM"
    schedule: list[CustomScheduleEntry] = Field(..., min_length=1)
    repeat_last_for_remaining: bool = True

    @model_validator(mode="after")
    def validate_schedule(self):
        amounts = [e.amount for e in self.schedule]
        if any(a <= 0 for a in amounts):
            raise ValueError("All scheduled amounts must be positive")
        return self


class LiftBasedContributionRule(BaseModel):
    """Lift-based installment — different amounts before/after lifting.
    
    Each member 'lifts' (receives the pot) in a specific period.
    Before their lift: pay pre_lift_amount
    After their lift: pay post_lift_amount
    """

    type: str = "LIFT_BASED"
    pre_lift_amount: Decimal = Field(..., gt=0, description="Amount paid before lifting")
    post_lift_amount: Decimal = Field(..., gt=0, description="Amount paid after lifting")


# Union type for contribution rules
ContributionRule = FixedContributionRule | VariableContributionRule | PercentageContributionRule | LiftBasedContributionRule


# ===========================================================================
# Payout Rules
# ===========================================================================


class ScheduledPayoutRule(BaseModel):
    """Payout in order — one member per period."""

    type: str = "SCHEDULED"
    payout_order: str = "MEMBER_NUMBER"  # MEMBER_NUMBER | AUCTION | RANDOM | CUSTOM
    commission_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    commission_fixed: Decimal = Field(default=Decimal("0"), ge=0)


class AuctionPayoutRule(BaseModel):
    """Auction-based payout — members bid for the pot."""

    type: str = "AUCTION"
    reserve_price_percentage: Decimal = Field(
        default=Decimal("80"), ge=0, le=100
    )
    commission_percentage: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    highest_bidder_wins: bool = True


class CustomPayoutScheduleEntry(BaseModel):
    period: int = Field(..., ge=1)
    member_number: int = Field(..., ge=1)


class CustomPayoutRule(BaseModel):
    """Custom payout order — explicitly mapped per period."""

    type: str = "CUSTOM"
    payout_schedule: list[CustomPayoutScheduleEntry] = Field(..., min_length=1)
    commission_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)


PayoutRule = ScheduledPayoutRule | AuctionPayoutRule | CustomPayoutRule


# ===========================================================================
# Fee Rules
# ===========================================================================


class FeeRules(BaseModel):
    """Optional fee configuration."""

    registration_fee: Decimal = Field(default=Decimal("0"), ge=0)
    monthly_management_fee: Decimal = Field(default=Decimal("0"), ge=0)
    late_fee_per_day: Decimal = Field(default=Decimal("0"), ge=0)
    late_fee_max_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)


# ===========================================================================
# Penalty Rules
# ===========================================================================


class PenaltyRules(BaseModel):
    """Optional penalty configuration."""

    grace_period_days: int = Field(default=0, ge=0)
    penalty_amount: Decimal = Field(default=Decimal("0"), ge=0)
    penalty_type: str = "FIXED"  # FIXED | PERCENTAGE | PROGRESSIVE
    max_penalty_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    auto_cancel_after_missed: Optional[int] = Field(None, ge=1)


# ===========================================================================
# Helpers
# ===========================================================================


def validate_contribution_rules(rules: dict) -> ContributionRule:
    """Validate and parse contribution rules from JSONB."""
    rule_type = rules.get("type", "FIXED")
    if rule_type == "FIXED":
        return FixedContributionRule(**rules)
    elif rule_type == "SCHEDULE":
        return VariableContributionRule(**rules)
    elif rule_type == "PERCENTAGE":
        return PercentageContributionRule(**rules)
    elif rule_type == "LIFT_BASED":
        return LiftBasedContributionRule(**rules)
    elif rule_type == "CUSTOM":
        return CustomContributionRule(**rules)
    else:
        raise ValueError(f"Unknown contribution rule type: {rule_type}")


def validate_payout_rules(rules: dict) -> PayoutRule:
    """Validate and parse payout rules from JSONB."""
    rule_type = rules.get("type", "SCHEDULED")
    if rule_type == "SCHEDULED":
        return ScheduledPayoutRule(**rules)
    elif rule_type == "AUCTION":
        return AuctionPayoutRule(**rules)
    elif rule_type == "CUSTOM":
        return CustomPayoutRule(**rules)
    else:
        raise ValueError(f"Unknown payout rule type: {rule_type}")
