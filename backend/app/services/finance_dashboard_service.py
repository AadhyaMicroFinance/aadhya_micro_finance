"""Finance-only dashboard projections.

Every value here is derived exclusively from finance_accounts,
finance_schedules and payment_transactions. Chitti data is never queried.
"""

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.finance import FinanceAccount, FinanceSchedule
from app.models.payment import PaymentTransaction
from app.utils.dates import add_months
from app.utils.timezone import today_ist



class FinanceDashboardService:
    """Read-only Finance dashboard built from the Finance ledgers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _amount(value) -> float:
        return float(value or Decimal("0"))

    async def get_dashboard(self, *, customer_id: Optional[UUID] = None) -> dict:
        today = today_ist()

        accounts_query = select(FinanceAccount).order_by(FinanceAccount.created_at.desc())
        if customer_id:
            accounts_query = accounts_query.where(FinanceAccount.customer_id == customer_id)
        accounts = list((await self.session.execute(accounts_query)).scalars().all())

        schedule_query = (
            select(FinanceSchedule, FinanceAccount, Customer)
            .join(FinanceAccount, FinanceAccount.id == FinanceSchedule.finance_account_id)
            .join(Customer, Customer.id == FinanceAccount.customer_id)
            .where(FinanceSchedule.status != "CANCELLED")
        )
        if customer_id:
            schedule_query = schedule_query.where(FinanceAccount.customer_id == customer_id)
        schedule_rows = (await self.session.execute(schedule_query)).all()

        payment_query = select(PaymentTransaction, Customer.full_name).outerjoin(
            Customer, Customer.id == PaymentTransaction.customer_id
        )
        if customer_id:
            payment_query = payment_query.where(PaymentTransaction.customer_id == customer_id)
        payment_rows = (await self.session.execute(payment_query)).all()

        total_principal = sum((a.principal_amount for a in accounts), Decimal("0"))
        status_distribution = Counter(a.status for a in accounts)

        outstanding = Decimal("0")
        pending = Decimal("0")
        overdue = Decimal("0")
        pending_count = 0
        overdue_count = 0
        expected_by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        upcoming: list[tuple[FinanceSchedule, FinanceAccount, Customer]] = []
        overdue_by_account: dict[UUID, dict] = {}

        for schedule, account, customer in schedule_rows:
            remaining = schedule.remaining_amount or Decimal("0")
            outstanding += remaining
            month = str(schedule.due_date)[:7]
            expected_by_month[month] += schedule.expected_amount or Decimal("0")

            # Match PaymentService.list_pending_collections: a schedule is due
            # once its due date arrives, regardless of whether its stored status
            # is still the initial UPCOMING label. CANCELLED rows were excluded
            # by the query above.
            if remaining > 0 and schedule.due_date <= today:
                pending += remaining
                pending_count += 1
                if schedule.due_date < today:
                    overdue += remaining
                    overdue_count += 1
                    entry = overdue_by_account.setdefault(
                        account.id,
                        {
                            "account_id": str(account.id),
                            "account_number": account.account_number,
                            "customer_id": str(customer.id),
                            "customer_name": customer.full_name,
                            "customer_code": customer.customer_code,
                            "mobile_number": customer.mobile_number,
                            "overdue_amount": Decimal("0"),
                            "overdue_installments": 0,
                            "oldest_due_date": str(schedule.due_date),
                        },
                    )
                    entry["overdue_amount"] += remaining
                    entry["overdue_installments"] += 1
                    if str(schedule.due_date) < entry["oldest_due_date"]:
                        entry["oldest_due_date"] = str(schedule.due_date)
            elif remaining > 0 and schedule.due_date > today:
                upcoming.append((schedule, account, customer))

        collections = Decimal("0")
        collection_count = 0
        collected_by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        recent_activity: list[dict] = []
        for payment, customer_name in payment_rows:
            if payment.status == "COMPLETED" and not payment.is_reversal:
                collections += payment.amount or Decimal("0")
                collection_count += 1
                month = str(payment.payment_date)[:7]
                collected_by_month[month] += payment.amount or Decimal("0")
            recent_activity.append(
                {
                    "id": str(payment.id),
                    "transaction_id": payment.transaction_id,
                    "type": "REVERSAL" if payment.is_reversal else "PAYMENT",
                    "customer_name": customer_name,
                    "customer_id": str(payment.customer_id),
                    "finance_account_id": (
                        str(payment.finance_account_id) if payment.finance_account_id else None
                    ),
                    "amount": self._amount(payment.amount),
                    "payment_method": payment.payment_method,
                    "payment_date": str(payment.payment_date),
                    "status": payment.status,
                    "is_reversal": payment.is_reversal,
                    "created_at": str(payment.created_at),
                }
            )

        recent_activity.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        upcoming.sort(key=lambda row: (row[0].due_date, row[2].full_name, row[0].installment_number))

        months = [
            str(add_months(date(today.year, today.month, 1), -offset))[:7]
            for offset in range(5, -1, -1)
        ]
        trends = [
            {
                "period": month,
                "expected": self._amount(expected_by_month.get(month)),
                "collected": self._amount(collected_by_month.get(month)),
            }
            for month in months
        ]

        return {
            "kpis": {
                "total_accounts": len(accounts),
                "total_principal_disbursed": self._amount(total_principal),
                "total_outstanding": self._amount(outstanding),
                "total_collections": self._amount(collections),
                "pending_repayments": self._amount(pending),
                "overdue_repayments": self._amount(overdue),
                # Explicit counts requested by the Finance dashboard UI.
                "pending_repayments_count": pending_count,
                "overdue_repayments_count": overdue_count,
                "overdue_accounts_count": len(overdue_by_account),
                "total_collections_count": collection_count,
            },
            "trends": trends,
            "status_distribution": [
                {"status": status, "count": count}
                for status, count in sorted(status_distribution.items())
            ],
            "recent_activity": recent_activity[:10],
            "upcoming_repayments": [
                {
                    "schedule_id": str(schedule.id),
                    "account_id": str(account.id),
                    "account_number": account.account_number,
                    "customer_id": str(customer.id),
                    "customer_name": customer.full_name,
                    "customer_code": customer.customer_code,
                    "mobile_number": customer.mobile_number,
                    "installment_number": schedule.installment_number,
                    "due_date": str(schedule.due_date),
                    "expected_amount": self._amount(schedule.expected_amount),
                    "remaining_amount": self._amount(schedule.remaining_amount),
                    "status": schedule.status,
                }
                for schedule, account, customer in upcoming[:10]
            ],
            "overdue_accounts": [
                {
                    **entry,
                    "overdue_amount": self._amount(entry["overdue_amount"]),
                }
                for entry in sorted(
                    overdue_by_account.values(),
                    key=lambda item: (item["oldest_due_date"], item["customer_name"]),
                )[:10]
            ],
        }
