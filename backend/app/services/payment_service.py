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

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    DuplicatePaymentException,
    NotFoundException,
    PaymentExceedsBalanceException,
)
from app.repositories.finance_repo import FinanceAccountRepository, FinanceScheduleRepository
from app.repositories.payment_repo import PaymentRepository
from app.models.customer import Customer
from app.models.payment import PaymentTransaction
from app.models.chitti import (
    Chitti,
    ChittiMember,
    ChittiMemberContribution,
    ChittiPeriodSchedule,
    ChittiTransaction,
)
from app.models.finance import FinanceAccount, FinanceSchedule
from app.utils.codes import generate_payment_id
from app.utils.timezone import today_ist


class PaymentService:
    """Payment processing with atomicity guarantees."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.finance_repo = FinanceAccountRepository(session)
        self.schedule_repo = FinanceScheduleRepository(session)

    async def list_pending_collections(self) -> list[dict]:
        """Return due, unpaid installments across the separate ledgers.

        This is a read-only projection. It never creates or reallocates a
        payment, and Chitti lift-based balances use the existing Chitti
        calculation service so the collection screen stays consistent with
        member schedules.
        """
        today = today_ist()
        records: list[dict] = []
        seen: set[tuple[str, str]] = set()

        finance_rows = (
            await self.session.execute(
                select(FinanceSchedule, FinanceAccount, Customer)
                .join(FinanceAccount, FinanceAccount.id == FinanceSchedule.finance_account_id)
                .join(Customer, Customer.id == FinanceAccount.customer_id)
                .where(
                    FinanceAccount.status == "ACTIVE",
                    FinanceSchedule.status != "CANCELLED",
                    FinanceSchedule.remaining_amount > 0,
                    FinanceSchedule.due_date <= today,
                )
                .order_by(FinanceSchedule.due_date, Customer.full_name, FinanceSchedule.installment_number)
            )
        ).all()

        for schedule, account, customer in finance_rows:
            key = ("FINANCE", str(schedule.id))
            if key in seen or schedule.remaining_amount <= 0:
                continue
            seen.add(key)
            status = (
                "PARTIALLY_PAID" if schedule.paid_amount > 0
                else "OVERDUE" if schedule.due_date < today
                else "DUE"
            )
            records.append({
                "id": f"FINANCE:{schedule.id}",
                "source": "FINANCE",
                "customer_id": str(customer.id),
                "customer_code": customer.customer_code,
                "customer_name": customer.full_name,
                "mobile_number": customer.mobile_number,
                "account_id": str(account.id),
                "account_name": account.account_number,
                "account_code": account.account_number,
                "schedule_id": str(schedule.id),
                "member_id": None,
                "period_number": schedule.installment_number,
                "due_date": str(schedule.due_date),
                "expected_amount": float(schedule.expected_amount),
                "outstanding_amount": float(schedule.remaining_amount),
                "status": status,
            })

        chitti_rows = (
            await self.session.execute(
                select(
                    ChittiMemberContribution,
                    ChittiPeriodSchedule,
                    ChittiMember,
                    Chitti,
                    Customer,
                )
                .join(ChittiMember, ChittiMember.id == ChittiMemberContribution.member_id)
                .join(Chitti, Chitti.id == ChittiMemberContribution.chitti_id)
                .join(Customer, Customer.id == ChittiMember.customer_id)
                .join(
                    ChittiPeriodSchedule,
                    and_(
                        ChittiPeriodSchedule.chitti_id == Chitti.id,
                        ChittiPeriodSchedule.period_number == ChittiMemberContribution.period_number,
                    ),
                )
                .where(
                    Chitti.status == "RUNNING",
                    ChittiMember.status == "ACTIVE",
                    ChittiMemberContribution.status != "WAIVED",
                    ChittiPeriodSchedule.due_date <= today,
                )
                .order_by(ChittiPeriodSchedule.due_date, Customer.full_name, ChittiMemberContribution.period_number)
            )
        ).all()

        grouped: dict[str, tuple[Chitti, list[tuple]]] = {}
        for contribution, period, member, chitti, customer in chitti_rows:
            group = grouped.setdefault(str(chitti.id), (chitti, []))
            group[1].append((contribution, period, member, customer))

        if grouped:
            from app.services.chitti_service import ChittiService

            chitti_service = ChittiService(self.session)
            for chitti, rows in grouped.values():
                contributions = [row[0] for row in rows]
                effective = await chitti_service._effective_contribution_values(chitti, contributions)
                for contribution, period, member, customer in rows:
                    values = effective[contribution.id]
                    remaining = values["remaining"]
                    if remaining <= 0:
                        continue
                    key = ("CHITTI", str(contribution.id))
                    if key in seen:
                        continue
                    seen.add(key)
                    paid = values["paid"]
                    status = (
                        "PARTIALLY_PAID" if paid > 0
                        else "OVERDUE" if period.due_date < today
                        else "DUE"
                    )
                    records.append({
                        "id": f"CHITTI:{contribution.id}",
                        "source": "CHITTI",
                        "customer_id": str(customer.id),
                        "customer_code": customer.customer_code,
                        "customer_name": customer.full_name,
                        "mobile_number": customer.mobile_number,
                        "account_id": str(chitti.id),
                        "account_name": chitti.name,
                        "account_code": chitti.chitti_code,
                        "schedule_id": None,
                        "member_id": str(member.id),
                        "period_number": contribution.period_number,
                        "due_date": str(period.due_date),
                        "expected_amount": float(values["expected"]),
                        "outstanding_amount": float(remaining),
                        "status": status,
                    })

        records.sort(key=lambda item: (item["due_date"], item["customer_name"].casefold(), item["source"], item["period_number"]))
        return records

    async def list_payment_history(
        self, *, page: int = 1, per_page: int = 25, customer_id: Optional[UUID] = None
    ) -> tuple[list[dict], int]:
        """Return Finance receipts and Chitti contribution ledger entries together.

        The ledgers stay separate in storage and accounting. This is a combined
        read model for the Payments history screen only.
        """
        skip = (page - 1) * per_page
        limit = skip + per_page

        finance_count_query = select(func.count()).select_from(PaymentTransaction)
        finance_query = (
            select(PaymentTransaction, Customer.full_name)
            .outerjoin(Customer, Customer.id == PaymentTransaction.customer_id)
            .order_by(PaymentTransaction.created_at.desc(), PaymentTransaction.id.desc())
            .limit(limit)
        )
        if customer_id:
            finance_count_query = finance_count_query.where(
                PaymentTransaction.customer_id == customer_id
            )
            finance_query = finance_query.where(
                PaymentTransaction.customer_id == customer_id
            )
        finance_total = (await self.session.execute(finance_count_query)).scalar_one()
        finance_rows = (await self.session.execute(finance_query)).all()

        chitti_types = ("CONTRIBUTION", "REVERSAL", "PENALTY", "FEE")
        chitti_count_query = select(func.count()).select_from(ChittiTransaction).where(
            ChittiTransaction.transaction_type.in_(chitti_types)
        )
        chitti_query = (
            select(
                ChittiTransaction,
                ChittiMember.customer_id,
                Customer.full_name,
                Chitti.name,
            )
            .outerjoin(ChittiMember, ChittiMember.id == ChittiTransaction.member_id)
            .outerjoin(Customer, Customer.id == ChittiMember.customer_id)
            .join(Chitti, Chitti.id == ChittiTransaction.chitti_id)
            .where(ChittiTransaction.transaction_type.in_(chitti_types))
            .order_by(ChittiTransaction.created_at.desc(), ChittiTransaction.id.desc())
            .limit(limit)
        )
        if customer_id:
            chitti_count_query = chitti_count_query.join(
                ChittiMember,
                ChittiMember.id == ChittiTransaction.member_id,
            ).where(ChittiMember.customer_id == customer_id)
            chitti_query = chitti_query.where(ChittiMember.customer_id == customer_id)
        chitti_total = (await self.session.execute(chitti_count_query)).scalar_one()
        chitti_rows = (await self.session.execute(chitti_query)).all()

        items: list[tuple[object, dict]] = []
        for payment, customer_name in finance_rows:
            items.append((payment.created_at, {
                "id": str(payment.id),
                "transaction_id": payment.transaction_id,
                "customer_id": str(payment.customer_id),
                "customer_name": customer_name,
                "finance_account_id": str(payment.finance_account_id) if payment.finance_account_id else None,
                "chitti_account_id": str(payment.chitti_account_id) if payment.chitti_account_id else None,
                "member_id": None,
                "member_name": None,
                "chitti_name": None,
                "period_number": None,
                "account_type": "FINANCE",
                "transaction_type": "REVERSAL" if payment.is_reversal else "PAYMENT",
                "amount": float(payment.amount),
                "payment_method": payment.payment_method,
                "payment_date": str(payment.payment_date),
                "reference_number": payment.reference_number,
                "notes": payment.notes,
                "status": payment.status,
                "is_reversal": payment.is_reversal,
                "collected_by": str(payment.collected_by) if payment.collected_by else None,
                "created_at": str(payment.created_at),
            }))

        for txn, linked_customer_id, customer_name, chitti_name in chitti_rows:
            is_reversal = txn.transaction_type == "REVERSAL"
            items.append((txn.created_at, {
                "id": str(txn.id),
                "transaction_id": f"CHT-{txn.id}",
                "customer_id": str(linked_customer_id) if linked_customer_id else None,
                "customer_name": customer_name,
                "finance_account_id": None,
                "chitti_account_id": str(txn.chitti_id),
                "member_id": str(txn.member_id) if txn.member_id else None,
                "member_name": customer_name,
                "chitti_name": chitti_name,
                "period_number": txn.period_number,
                "account_type": "CHITTI",
                "transaction_type": txn.transaction_type,
                "amount": float(txn.amount),
                "payment_method": txn.payment_method,
                "payment_date": str(txn.payment_date) if txn.payment_date else None,
                "reference_number": txn.reference_number,
                "notes": txn.notes,
                "status": "REVERSED" if is_reversal else "COMPLETED",
                "is_reversal": is_reversal,
                "collected_by": str(txn.created_by) if txn.created_by else None,
                "created_at": str(txn.created_at),
            }))

        items.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
        return [item for _, item in items[skip:limit]], finance_total + chitti_total

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

        if not finance_account_id:
            raise BadRequestException("Select a Finance account to record this payment.")
        if not finance_schedule_id:
            raise BadRequestException(
                "Select a Finance installment so the payment is allocated to the correct due.",
                error_code="FINANCE_SCHEDULE_REQUIRED",
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

        if finance_schedule_id:
            schedule = await self.schedule_repo.get_by_id(UUID(finance_schedule_id))
            if not schedule:
                raise NotFoundException("Finance schedule", finance_schedule_id)
            if schedule.finance_account_id != account.id:
                raise BadRequestException("Schedule does not belong to the selected Finance account.")
            if schedule.remaining_amount <= 0:
                raise BadRequestException("This installment is already fully paid.")
            if amount > schedule.remaining_amount:
                raise PaymentExceedsBalanceException(
                    float(schedule.remaining_amount), float(amount)
                )

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
            raise NotFoundException("Finance schedule", schedule_id)

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

        from app.utils.timezone import today_ist

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
            payment_date=today_ist(),
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

        from app.services.audit_service import AuditService
        await AuditService(self.session).log(
            user_id=reversed_by,
            action="FINANCE_PAYMENT_REVERSED",
            entity_type="payment_transaction",
            entity_id=reversal.id,
            previous_value={"payment_id": str(original.id), "amount": str(original.amount)},
            new_value={"reversal_id": str(reversal.id), "reason": reversal_reason},
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
