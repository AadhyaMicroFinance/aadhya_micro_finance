"""
Configurable Financial Calculation Engine.

All financial calculations are centralized here.
Business rules are configurable, not hard-coded.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.utils.timezone import today_ist


class CalculationEngine:
    """
    Centralized calculation engine for finance and chitti accounts.
    All monetary values use Decimal for precision.
    """

    # Frequency multipliers for due date calculation
    FREQUENCY_DAYS = {
        "DAILY": 1,
        "WEEKLY": 7,
        "MONTHLY": 30,
    }

    def calculate_finance_totals(
        self,
        principal_amount: Decimal,
        interest_rate: Decimal,
        interest_type: str,
        fees: Decimal,
        number_of_installments: int,
        custom_installment_amount: Optional[Decimal] = None,
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate total payable and installment amount.

        Returns:
            (total_payable, installment_amount)
        """
        interest_amount = self._calculate_interest(
            principal_amount, interest_rate, interest_type
        )
        total_payable = principal_amount + interest_amount + fees

        if custom_installment_amount and custom_installment_amount > 0:
            installment_amount = custom_installment_amount
        else:
            installment_amount = (
                total_payable / Decimal(number_of_installments)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return total_payable, installment_amount

    def _calculate_interest(
        self,
        principal: Decimal,
        rate: Decimal,
        interest_type: str,
    ) -> Decimal:
        """
        Calculate interest based on type.

        FLAT: Interest = Principal × Rate% × (Tenor in months / 12)
              Simplified: for flat rate, interest is on full principal.

        REDUCING: For reducing balance, average outstanding ≈ principal / 2
                  (simplified approximation for schedule generation).
        """
        if rate == 0:
            return Decimal("0")

        rate_decimal = rate / Decimal("100")

        if interest_type == "FLAT":
            # Flat rate: interest on full principal
            interest = (principal * rate_decimal).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        elif interest_type == "REDUCING":
            # Reducing balance approximation for schedule generation
            # Actual reducing balance is per-installment; this is the total estimate
            interest = (principal * rate_decimal / Decimal("2")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            interest = Decimal("0")

        return interest

    def generate_schedule(
        self,
        account_id,
        installment_amount: Decimal,
        first_due_date: date,
        number_of_installments: int,
        frequency: str,
    ) -> list[dict]:
        """
        Generate payment schedule entries.
        Returns list of dicts ready for FinanceSchedule creation.
        """
        days = self.FREQUENCY_DAYS.get(frequency, 30)
        schedule = []

        for i in range(1, number_of_installments + 1):
            due_date = first_due_date + timedelta(days=days * (i - 1))
            schedule.append({
                "finance_account_id": account_id,
                "installment_number": i,
                "due_date": due_date,
                "expected_amount": installment_amount,
                "paid_amount": Decimal("0"),
                "remaining_amount": installment_amount,
                "status": "UPCOMING",
            })

        return schedule

    def allocate_payment(
        self,
        payment_amount: Decimal,
        pending_schedules: list,
        advance_policy: str = "AUTO_ALLOCATE",
    ) -> list[dict]:
        """
        Allocate a payment across pending installments.

        Args:
            payment_amount: Total payment received
            pending_schedules: List of schedule objects with remaining_amount > 0
            advance_policy: AUTO_ALLOCATE or HOLD_AS_CREDIT

        Returns:
            List of allocations: [{"schedule_id": UUID, "allocated_amount": Decimal, ...}]
        """
        allocations = []
        remaining_payment = payment_amount

        for schedule in pending_schedules:
            if remaining_payment <= 0:
                break

            if advance_policy == "HOLD_AS_CREDIT" and schedule.status == "UPCOMING":
                # Don't auto-allocate to upcoming if holding as credit
                continue

            amount_to_allocate = min(remaining_payment, schedule.remaining_amount)
            allocations.append({
                "schedule_id": schedule.id,
                "allocated_amount": amount_to_allocate,
            })
            remaining_payment -= amount_to_allocate

        # Any remaining payment after all installments = advance credit
        if remaining_payment > 0:
            allocations.append({
                "schedule_id": None,
                "allocated_amount": remaining_payment,
                "is_advance": True,
            })

        return allocations

    def calculate_balance(self, total_payable: Decimal, payments: list) -> dict:
        """
        Calculate balance from transaction ledger.
        Never rely on stored balance values.
        """
        total_paid = sum(
            p.amount for p in payments
            if p.status == "COMPLETED" and not p.is_reversal
        )
        total_reversed = sum(
            p.amount for p in payments
            if p.status == "REVERSED"
        )
        effective_paid = total_paid - total_reversed
        outstanding = total_payable - effective_paid

        return {
            "total_payable": total_payable,
            "total_paid": effective_paid,
            "outstanding": max(outstanding, Decimal("0")),
            "is_fully_paid": outstanding <= 0,
        }
