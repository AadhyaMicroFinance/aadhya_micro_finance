"""
Payment service — orchestrates the complete payment flow.

This is the most critical service. It ensures atomicity:
1. Validate payment
2. Check idempotency
3. Record transaction
4. Update schedule
5. Recalculate balance
6. All within a single database transaction
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    DuplicatePaymentException,
    NotFoundException,
    PaymentExceedsBalanceException,
)
from app.repositories.finance_repo import FinanceAccountRepository, FinanceScheduleRepository
from app.repositories.payment_repo import PaymentRepository
from app.utils.codes import generate_payment_id


class PaymentService:
    """Payment processing with atomicity guarantees."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.finance_repo = FinanceAccountRepository(session)
        self.schedule_repo = FinanceScheduleRepository(session)

    async def record_payment(
        self,
        *,
        customer_id: str,
        finance_account_id: Optional[str] = None,
        chitti_account_id: Optional[str] = None,
        finance_schedule_id: Optional[str] = None,
        chitti_schedule_id: Optional[str] = None,
        amount: Decimal,
        payment_method: str,
        payment_date,
        reference_number: Optional[str] = None,
        notes: Optional[str] = None,
        idempotency_key: str,
        collected_by: Optional[UUID] = None,
    ) -> dict:
        """
        Record a payment with full validation and atomic update.

        This method must be called within an active database transaction.
        The session's commit happens in the API layer or calling service.
        """
        # 1. Check idempotency
        existing = await self.payment_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            raise DuplicatePaymentException()

        # 2. Chitti money must never enter the finance ledger. Recording it here
        # would count the same collection twice (finance ledger + chitti ledger)
        # and leave the member's contribution row untouched.
        if chitti_account_id or chitti_schedule_id:
            raise BadRequestException(
                "Chitti contributions must be recorded through the Chitti contribution "
                "endpoint so member balances and period totals stay in sync.",
                error_code="USE_CHITTI_CONTRIBUTION_ENDPOINT",
            )

        # 3. Validate finance account if provided
        if finance_account_id:
            account = await self.finance_repo.get_by_id(UUID(finance_account_id))
            if not account:
                raise NotFoundException("Finance account", finance_account_id)
            if account.status != "ACTIVE":
                raise BadRequestException("Finance account is not active.")
            if str(account.customer_id) != customer_id:
                raise BadRequestException("Account does not belong to this customer.")

        # 3. Generate unique transaction ID
        transaction_id = await generate_payment_id(self.session)

        # 4. Record payment
        payment = await self.payment_repo.create(
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
            customer_id=UUID(customer_id),
            finance_account_id=UUID(finance_account_id) if finance_account_id else None,
            chitti_account_id=UUID(chitti_account_id) if chitti_account_id else None,
            finance_schedule_id=UUID(finance_schedule_id) if finance_schedule_id else None,
            chitti_schedule_id=UUID(chitti_schedule_id) if chitti_schedule_id else None,
            amount=amount,
            payment_method=payment_method,
            payment_date=payment_date,
            reference_number=reference_number,
            notes=notes,
            collected_by=collected_by,
            status="COMPLETED",
            is_reversal=False,
        )

        # 5. Update schedule if applicable
        if finance_schedule_id:
            await self._update_finance_schedule(
                UUID(finance_schedule_id), amount
            )

        return {
            "id": str(payment.id),
            "transaction_id": payment.transaction_id,
            "customer_id": str(payment.customer_id),
            "finance_account_id": str(payment.finance_account_id) if payment.finance_account_id else None,
            "chitti_account_id": str(payment.chitti_account_id) if payment.chitti_account_id else None,
            "amount": float(payment.amount),
            "payment_method": payment.payment_method,
            "payment_date": str(payment.payment_date),
            "reference_number": payment.reference_number,
            "notes": payment.notes,
            "is_reversal": payment.is_reversal,
            "status": payment.status,
            "collected_by": str(payment.collected_by) if payment.collected_by else None,
            "created_at": str(payment.created_at),
        }

    async def _update_finance_schedule(
        self, schedule_id: UUID, payment_amount: Decimal
    ) -> None:
        """Update a finance schedule entry after payment."""
        schedule = await self.schedule_repo.get_by_id(schedule_id)
        if not schedule:
            return

        new_paid = schedule.paid_amount + payment_amount
        new_remaining = schedule.expected_amount - new_paid

        if new_remaining <= 0:
            status = "PAID"
            from app.utils.timezone import now_ist
            completed_at = now_ist()
        elif new_paid > 0:
            status = "PARTIALLY_PAID"
            completed_at = None
        else:
            status = schedule.status
            completed_at = None

        await self.schedule_repo.update(
            schedule,
            paid_amount=new_paid,
            remaining_amount=max(new_remaining, Decimal("0")),
            status=status,
            completed_at=completed_at,
        )

    async def _restore_finance_schedule(
        self, schedule_id: UUID, payment_amount: Decimal
    ) -> None:
        """Undo the allocation a payment made to its installment."""
        from app.utils.timezone import today_ist

        schedule = await self.schedule_repo.get_by_id(schedule_id)
        if not schedule:
            return

        new_paid = max(schedule.paid_amount - payment_amount, Decimal("0"))
        new_remaining = schedule.expected_amount - new_paid

        if new_paid <= 0:
            status = "OVERDUE" if schedule.due_date < today_ist() else "UPCOMING"
            completed_at = None
        elif new_remaining > 0:
            status = "PARTIALLY_PAID"
            completed_at = None
        else:
            status = "PAID"
            completed_at = schedule.completed_at

        await self.schedule_repo.update(
            schedule,
            paid_amount=new_paid,
            remaining_amount=max(new_remaining, Decimal("0")),
            status=status,
            completed_at=completed_at,
        )

    async def reverse_payment(
        self,
        payment_id: UUID,
        *,
        reversal_reason: str,
        reversed_by: UUID,
    ) -> dict:
        """
        Reverse a payment (does not delete the original).
        Creates a new reversal transaction.
        """
        original = await self.payment_repo.get_by_id(payment_id)
        if not original:
            raise NotFoundException("Payment", payment_id)
        if original.is_reversal:
            raise BadRequestException("Cannot reverse a reversal transaction.")
        if original.status == "REVERSED":
            raise BadRequestException("Payment is already reversed.")

        # Create reversal transaction
        reversal_id = await generate_payment_id(self.session)
        reversal = await self.payment_repo.create(
            transaction_id=reversal_id,
            idempotency_key=f"reversal-{original.idempotency_key}",
            customer_id=original.customer_id,
            finance_account_id=original.finance_account_id,
            chitti_account_id=original.chitti_account_id,
            finance_schedule_id=original.finance_schedule_id,
            chitti_schedule_id=original.chitti_schedule_id,
            amount=original.amount,
            payment_method=original.payment_method,
            payment_date=original.payment_date,
            notes=reversal_reason,
            collected_by=reversed_by,
            status="REVERSED",
            is_reversal=True,
            reversed_by=original.id,
            reversal_reason=reversal_reason,
        )

        # Mark original as reversed
        await self.payment_repo.update(original, status="REVERSED")

        # Undo the installment allocation, otherwise the schedule keeps showing
        # money that was handed back and the customer looks overpaid forever.
        if original.finance_schedule_id:
            await self._restore_finance_schedule(
                original.finance_schedule_id, original.amount
            )

        return {
            "id": str(reversal.id),
            "transaction_id": reversal.transaction_id,
            "original_transaction_id": original.transaction_id,
            "amount": float(reversal.amount),
            "status": reversal.status,
            "reversal_reason": reversal.reversal_reason,
        }

    async def get_due_info(
        self, customer_id: str, finance_account_id: str
    ) -> dict:
        """Get payment due information for an account."""
        account = await self.finance_repo.get_by_id(UUID(finance_account_id))
        if not account:
            raise NotFoundException("Finance account", finance_account_id)

        # Calculate from ledger
        from app.services.calculation_engine import CalculationEngine
        calc = CalculationEngine()

        payments = await self.payment_repo.get_by_finance_account_id(
            UUID(finance_account_id)
        )
        balance = calc.calculate_balance(account.total_payable, payments)

        # Get next due schedule
        next_schedule = await self.schedule_repo.get_upcoming_due(
            UUID(finance_account_id)
        )

        return {
            "account_id": str(account.id),
            "account_number": account.account_number,
            "account_type": "FINANCE",
            "amount_due": float(next_schedule.expected_amount) if next_schedule else 0,
            "outstanding": float(balance["outstanding"]),
            "next_due_date": str(next_schedule.due_date) if next_schedule else None,
            "next_installment_number": next_schedule.installment_number if next_schedule else None,
            "total_paid": float(balance["total_paid"]),
            "total_payable": float(balance["total_payable"]),
        }
