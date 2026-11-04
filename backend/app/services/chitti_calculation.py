"""
Chitti Calculation Engine — Strategy Pattern.

All financial calculations for Chitti are centralized here.
Each Chitti type plugs in its own strategy for contributions and payouts.

NEVER use float for money — always Decimal.
"""

from abc import ABC, abstractmethod
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.core.chitti_rules import (
    AuctionPayoutRule,
    ContributionRule,
    CustomPayoutRule,
    FixedContributionRule,
    FeeRules,
    PayoutRule,
    PenaltyRules,
    ScheduledPayoutRule,
    VariableContributionRule,
)


# ===========================================================================
# Contribution Strategies
# ===========================================================================


class ContributionStrategy(ABC):
    """Interface for contribution calculation."""

    @abstractmethod
    def calculate_installment(
        self, period: int, total_periods: int, total_value: Decimal, member_count: int
    ) -> Decimal:
        """Calculate the expected contribution amount for a given period."""
        ...

    @abstractmethod
    def calculate_total_contribution(self, total_value: Decimal, member_count: int) -> Decimal:
        """Total expected contribution per member across all periods."""
        ...


class FixedContributionStrategy(ContributionStrategy):
    """Fixed installment for every period."""

    def __init__(self, rule: FixedContributionRule):
        self.rule = rule

    def calculate_installment(
        self, period: int, total_periods: int, total_value: Decimal, member_count: int
    ) -> Decimal:
        if self.rule.first_installment_different and period == 1 and self.rule.first_installment_amount:
            return self.rule.first_installment_amount
        if self.rule.last_installment_different and period == total_periods and self.rule.last_installment_amount:
            return self.rule.last_installment_amount
        return self.rule.installment_amount

    def calculate_total_contribution(self, total_value: Decimal, member_count: int) -> Decimal:
        return self.rule.installment_amount


class VariableContributionStrategy(ContributionStrategy):
    """Variable installment from explicit schedule."""

    def __init__(self, rule: VariableContributionRule, total_periods: int):
        self.rule = rule
        self.total_periods = total_periods
        # Build a lookup: period -> amount
        self._schedule: dict[int, Decimal] = {e.period: e.amount for e in rule.schedule}

    def calculate_installment(
        self, period: int, total_periods: int, total_value: Decimal, member_count: int
    ) -> Decimal:
        if period in self._schedule:
            return self._schedule[period]
        if self.rule.repeat_last_for_remaining and self.rule.schedule:
            # Repeat the last defined amount
            max_period = max(self._schedule.keys())
            if period > max_period:
                return self._schedule[max_period]
        # Default: divide remaining evenly
        return Decimal("0")

    def calculate_total_contribution(self, total_value: Decimal, member_count: int) -> Decimal:
        return sum(self._schedule.values())


class CustomContributionStrategy(ContributionStrategy):
    """Custom installment — admin defines exact amount per period."""

    def __init__(self, rule: "CustomContributionRule", total_periods: int):
        self.rule = rule
        self.total_periods = total_periods
        self._schedule: dict[int, Decimal] = {e.period: e.amount for e in rule.schedule}

    def calculate_installment(
        self, period: int, total_periods: int, total_value: Decimal, member_count: int
    ) -> Decimal:
        if period in self._schedule:
            return self._schedule[period]
        if self.rule.repeat_last_for_remaining and self._schedule:
            max_period = max(self._schedule.keys())
            if period > max_period:
                return self._schedule[max_period]
        return Decimal("0")

    def calculate_total_contribution(self, total_value: Decimal, member_count: int) -> Decimal:
        return sum(self._schedule.values())


class LiftBasedContributionStrategy(ContributionStrategy):
    """Lift-based installment — different amounts before/after lifting.
    
    Each member has a lift period (their payout_order).
    - Before their lift period: pay pre_lift_amount
    - At and after their lift period: pay post_lift_amount
    """

    def __init__(self, rule: "LiftBasedContributionRule"):
        self.rule = rule

    def calculate_installment(
        self, period: int, total_periods: int, total_value: Decimal, member_count: int
    ) -> Decimal:
        # Default (no member context): return pre-lift amount
        return self.rule.pre_lift_amount

    def calculate_installment_for_member(
        self, period: int, total_periods: int, total_value: Decimal,
        member_count: int, member_lift_period: int
    ) -> Decimal:
        """Calculate installment for a specific member based on their lift period.
        
        Args:
            member_lift_period: The period number when this member lifts (receives pot).
                               Period numbers are 1-indexed.
        """
        if period >= member_lift_period:
            return self.rule.post_lift_amount
        return self.rule.pre_lift_amount

    def calculate_total_contribution(self, total_value: Decimal, member_count: int) -> Decimal:
        return self.rule.pre_lift_amount


class PercentageContributionStrategy(ContributionStrategy):
    """Installment as percentage of total value."""

    def __init__(self, rule: "PercentageContributionRule"):
        self.rule = rule

    def calculate_installment(
        self, period: int, total_periods: int, total_value: Decimal, member_count: int
    ) -> Decimal:
        amount = (total_value * self.rule.percentage_of_total / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if self.rule.min_amount and amount < self.rule.min_amount:
            amount = self.rule.min_amount
        if self.rule.max_amount and amount > self.rule.max_amount:
            amount = self.rule.max_amount
        return amount

    def calculate_total_contribution(self, total_value: Decimal, member_count: int) -> Decimal:
        return self.rule.percentage_of_total


# ===========================================================================
# Payout Strategies
# ===========================================================================


class PayoutStrategy(ABC):
    """Interface for payout calculation."""

    @abstractmethod
    def get_payout_for_period(
        self,
        period: int,
        total_periods: int,
        total_collected: Decimal,
        member_count: int,
        member_number: Optional[int] = None,
    ) -> dict:
        """Calculate payout details for a given period.
        
        Returns:
            {
                "gross_payout": Decimal,
                "discount_amount": Decimal,
                "fee_amount": Decimal,
                "net_payout": Decimal,
                "member_number": int (who gets the payout),
            }
        """
        ...


class ScheduledPayoutStrategy(PayoutStrategy):
    """Payout in member-number order, one per period."""

    def __init__(self, rule: ScheduledPayoutRule):
        self.rule = rule

    def get_payout_for_period(
        self,
        period: int,
        total_periods: int,
        total_collected: Decimal,
        member_count: int,
        member_number: Optional[int] = None,
    ) -> dict:
        # Determine who gets payout this period
        if self.rule.payout_order == "MEMBER_NUMBER":
            payout_member = ((period - 1) % member_count) + 1
        else:
            payout_member = member_number or period

        gross = total_collected
        commission_pct = (self.rule.commission_percentage or Decimal("0")) / Decimal("100")
        commission_amount = (gross * commission_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        commission_amount += self.rule.commission_fixed or Decimal("0")

        net = gross - commission_amount
        return {
            "gross_payout": gross,
            "discount_amount": Decimal("0"),
            "fee_amount": commission_amount,
            "net_payout": max(net, Decimal("0")),
            "member_number": payout_member,
        }


class AuctionPayoutStrategy(PayoutStrategy):
    """Auction-based payout — discount from auction bid."""

    def __init__(self, rule: AuctionPayoutRule):
        self.rule = rule

    def get_payout_for_period(
        self,
        period: int,
        total_periods: int,
        total_collected: Decimal,
        member_count: int,
        member_number: Optional[int] = None,
    ) -> dict:
        # In auction, the discount (auction winning bid) reduces the payout
        gross = total_collected
        reserve = (gross * self.rule.reserve_price_percentage / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        # Discount = gross - reserve (simplified; real auction sets actual discount)
        discount = gross - reserve
        commission_pct = (self.rule.commission_percentage or Decimal("0")) / Decimal("100")
        fee = (gross * commission_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net = gross - discount - fee

        return {
            "gross_payout": gross,
            "discount_amount": discount,
            "fee_amount": fee,
            "net_payout": max(net, Decimal("0")),
            "member_number": member_number or period,
        }


class CustomPayoutStrategy(PayoutStrategy):
    """Custom payout order from explicit schedule."""

    def __init__(self, rule: CustomPayoutRule):
        self.rule = rule
        self._schedule: dict[int, int] = {e.period: e.member_number for e in rule.payout_schedule}

    def get_payout_for_period(
        self,
        period: int,
        total_periods: int,
        total_collected: Decimal,
        member_count: int,
        member_number: Optional[int] = None,
    ) -> dict:
        payout_member = self._schedule.get(period, member_number or period)
        commission_pct = (self.rule.commission_percentage or Decimal("0")) / Decimal("100")
        fee = (total_collected * commission_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net = total_collected - fee

        return {
            "gross_payout": total_collected,
            "discount_amount": Decimal("0"),
            "fee_amount": fee,
            "net_payout": max(net, Decimal("0")),
            "member_number": payout_member,
        }


# ===========================================================================
# Frequency Utilities
# ===========================================================================

FREQUENCY_DAYS = {
    "DAILY": 1,
    "WEEKLY": 7,
    "BIWEEKLY": 14,
    "MONTHLY": 30,
}


def get_due_dates(
    start_date: date,
    frequency: str,
    total_periods: int,
) -> list[date]:
    """Generate due dates for each period based on frequency."""
    days = FREQUENCY_DAYS.get(frequency, 30)
    return [start_date + timedelta(days=days * i) for i in range(total_periods)]


# ===========================================================================
# Main Calculation Engine
# ===========================================================================


class ChittiCalculationEngine:
    """
    Orchestrates all Chitti financial calculations.
    
    Usage:
        engine = ChittiCalculationEngine(plan_snapshot)
        schedule = engine.generate_period_schedule(start_date, member_count)
        installment = engine.get_contribution_for_period(period)
        payout = engine.get_payout_for_period(period, total_collected, member_count)
    """

    def __init__(self, plan_snapshot: dict):
        self.plan = plan_snapshot
        self._contribution_strategy: Optional[ContributionStrategy] = None
        self._payout_strategy: Optional[PayoutStrategy] = None

    @property
    def contribution_strategy(self) -> ContributionStrategy:
        if self._contribution_strategy is None:
            self._contribution_strategy = self._build_contribution_strategy()
        return self._contribution_strategy

    @property
    def payout_strategy(self) -> PayoutStrategy:
        if self._payout_strategy is None:
            self._payout_strategy = self._build_payout_strategy()
        return self._payout_strategy

    def _build_contribution_strategy(self) -> ContributionStrategy:
        rules = self.plan.get("contribution_rules", {})
        rule_type = rules.get("type", "FIXED")
        duration = self.plan.get("duration", 12)

        if rule_type == "FIXED":
            return FixedContributionStrategy(FixedContributionRule(**rules))
        elif rule_type == "SCHEDULE":
            return VariableContributionStrategy(
                VariableContributionRule(**rules), total_periods=duration
            )
        elif rule_type == "PERCENTAGE":
            from app.core.chitti_rules import PercentageContributionRule
            return PercentageContributionStrategy(PercentageContributionRule(**rules))
        elif rule_type == "LIFT_BASED":
            from app.core.chitti_rules import LiftBasedContributionRule
            return LiftBasedContributionStrategy(LiftBasedContributionRule(**rules))
        elif rule_type == "CUSTOM":
            from app.core.chitti_rules import CustomContributionRule
            return CustomContributionStrategy(CustomContributionRule(**rules), total_periods=duration)
        else:
            raise ValueError(f"Unknown contribution rule type: {rule_type}")

    def _build_payout_strategy(self) -> PayoutStrategy:
        rules = self.plan.get("payout_rules", {})
        rule_type = rules.get("type", "SCHEDULED")

        if rule_type == "SCHEDULED":
            return ScheduledPayoutStrategy(ScheduledPayoutRule(**rules))
        elif rule_type == "AUCTION":
            return AuctionPayoutStrategy(AuctionPayoutRule(**rules))
        elif rule_type == "CUSTOM":
            return CustomPayoutStrategy(CustomPayoutRule(**rules))
        else:
            raise ValueError(f"Unknown payout rule type: {rule_type}")

    def get_contribution_for_period(self, period: int) -> Decimal:
        """Expected contribution per member for a given period."""
        total_value = Decimal(str(self.plan.get("total_value", 0)))
        member_count = self.plan.get("member_count", 1)
        duration = self.plan.get("duration", 1)
        return self.contribution_strategy.calculate_installment(
            period, duration, total_value, member_count
        )

    def generate_period_schedule(
        self, start_date: date, member_count: int
    ) -> list[dict]:
        """Generate period-level schedule (one row per period).
        
        Returns list of dicts ready for ChittiPeriodSchedule creation.
        """
        duration = self.plan.get("duration", 1)
        frequency = self.plan.get("frequency", "MONTHLY")
        total_value = Decimal(str(self.plan.get("total_value", 0)))
        due_dates = get_due_dates(start_date, frequency, duration)

        schedule = []
        for i, due_date in enumerate(due_dates, start=1):
            installment = self.contribution_strategy.calculate_installment(
                i, duration, total_value, member_count
            )
            expected_collection = installment * Decimal(str(member_count))

            schedule.append({
                "period_number": i,
                "due_date": due_date,
                "expected_collection": expected_collection,
                "pending_collection": expected_collection,
                "expected_payout": Decimal("0"),  # filled by payout strategy
                "actual_payout": Decimal("0"),
                "status": "UPCOMING",
            })
        return schedule

    def generate_member_contributions(
        self, member_id, member_number: int, start_date: date,
        member_lift_period: int | None = None,
    ) -> list[dict]:
        """Generate per-member contribution schedule for all periods.
        
        For LIFT_BASED rules, member_lift_period determines pre/post amounts.
        If not provided, defaults to member_number (members lift in order).
        """
        duration = self.plan.get("duration", 1)
        frequency = self.plan.get("frequency", "MONTHLY")
        total_value = Decimal(str(self.plan.get("total_value", 0)))
        member_count = self.plan.get("member_count", 1)
        due_dates = get_due_dates(start_date, frequency, duration)

        # Determine lift period for this member
        lift_period = member_lift_period or member_number

        contributions = []
        for i, due_date in enumerate(due_dates, start=1):
            # Check if strategy supports per-member calculation
            if hasattr(self.contribution_strategy, "calculate_installment_for_member"):
                expected = self.contribution_strategy.calculate_installment_for_member(
                    i, duration, total_value, member_count, lift_period
                )
            else:
                expected = self.contribution_strategy.calculate_installment(
                    i, duration, total_value, member_count
                )
            contributions.append({
                "chitti_id": None,  # set by caller
                "member_id": member_id,
                "period_number": i,
                "expected_amount": expected,
                "paid_amount": Decimal("0"),
                "remaining_amount": expected,
                "status": "UPCOMING",
            })
        return contributions

    def get_payout_for_period(
        self,
        period: int,
        total_collected: Decimal,
        member_count: int,
        member_number: Optional[int] = None,
    ) -> dict:
        """Calculate payout for a given period."""
        duration = self.plan.get("duration", 1)
        return self.payout_strategy.get_payout_for_period(
            period, duration, total_collected, member_count, member_number
        )

    def preview_full_schedule(self, start_date: date, member_count: int) -> dict:
        """Generate a complete preview of the chitti for admin review before creation.
        
        Returns:
            {
                "periods": [...],
                "total_expected_collection": Decimal,
                "total_expected_payout": Decimal,
                "per_member_installment_schedule": [...],
            }
        """
        schedule = self.generate_period_schedule(start_date, member_count)
        total_collection = sum(s["expected_collection"] for s in schedule)
        total_payout = sum(s["expected_payout"] for s in schedule)

        # Per-member installment preview
        duration = self.plan.get("duration", 1)
        tv = Decimal(str(self.plan.get("total_value", 0)))
        member_installments = []
        if hasattr(self.contribution_strategy, "calculate_installment_for_member"):
            # Lift-based: show sample for member #1 (lifts first) and last member
            sample_members = [1, member_count] if member_count > 1 else [1]
            for member_num in sample_members:
                member_schedule = []
                for period in range(1, duration + 1):
                    amount = self.contribution_strategy.calculate_installment_for_member(
                        period, duration, tv, member_count, member_num
                    )
                    due_date = schedule[period - 1]["due_date"] if period <= len(schedule) else None
                    member_schedule.append({
                        "period": period,
                        "due_date": str(due_date) if due_date else None,
                        "amount": amount,
                    })
                member_installments.append({
                    "member_number": member_num,
                    "lift_period": member_num,
                    "schedule": member_schedule,
                    "total": sum(e["amount"] for e in member_schedule),
                })
        else:
            # Fixed/Variable: same schedule for all
            for period in range(1, duration + 1):
                amount = self.get_contribution_for_period(period)
                due_date = schedule[period - 1]["due_date"] if period <= len(schedule) else None
                member_installments.append({
                    "period": period,
                    "due_date": str(due_date) if due_date else None,
                    "amount": amount,
                })

        return {
            "periods": [
                {
                    "period_number": s["period_number"],
                    "due_date": str(s["due_date"]),
                    "expected_collection": s["expected_collection"],
                    "expected_payout": s["expected_payout"],
                    "status": s["status"],
                }
                for s in schedule
            ],
            "total_expected_collection": total_collection,
            "total_expected_payout": total_payout,
            "per_member_installment_schedule": member_installments,
        }


# ===========================================================================
# Fee & Penalty Helpers
# ===========================================================================


def calculate_late_fee(
    overdue_days: int,
    penalty_rules: dict,
    outstanding_amount: Decimal,
) -> Decimal:
    """Calculate late fee based on penalty rules."""
    if not penalty_rules:
        return Decimal("0")

    grace = penalty_rules.get("grace_period_days", 0)
    effective_days = max(0, overdue_days - grace)

    if effective_days <= 0:
        return Decimal("0")

    penalty_type = penalty_rules.get("penalty_type", "FIXED")
    penalty_amount = Decimal(str(penalty_rules.get("penalty_amount", 0)))
    max_pct = Decimal(str(penalty_rules.get("max_penalty_percentage", 0))) / Decimal("100")

    if penalty_type == "FIXED":
        fee = penalty_amount * Decimal(str(effective_days))
    elif penalty_type == "PERCENTAGE":
        fee = (outstanding_amount * penalty_amount / Decimal("100")) * Decimal(str(effective_days))
    else:
        fee = penalty_amount * Decimal(str(effective_days))

    # Cap at max percentage
    if max_pct > 0:
        max_fee = outstanding_amount * max_pct
        fee = min(fee, max_fee)

    return fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_total_per_member(total_value: Decimal, member_count: int, duration: int) -> Decimal:
    """Contribution per member per period for a simple fixed chitti."""
    return (total_value / Decimal(str(member_count))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
