"""
Report service — calendar-based collection metrics.

Everything here is keyed off a calendar date (business timezone IST):
  - Expected today  → finance schedules + chitti period schedules due that day
  - Collected today → payments recorded that day (net of reversals)
  - Net collections  → collected minus reversals for the day
  - By user         → collections grouped by the collector who recorded them
  - Pending         → what was due that day but not fully collected

All money is Decimal. Never float.
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chitti import ChittiPeriodSchedule
from app.models.customer import Customer
from app.models.finance import FinanceSchedule
from app.models.payment import PaymentTransaction
from app.models.user import User
from app.utils.timezone import today_ist


class ReportService:
    """Business logic for calendar-based reporting."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ===========================================================================
    # Daily summary (headline metrics for the dashboard)
    # ===========================================================================

    async def get_daily_summary(self, report_date: Optional[date] = None) -> dict:
        """Headline metrics for a single calendar day."""
        d = report_date or today_ist()

        expected = await self._expected_for_date(d)
        collected = await self._collected_for_date(d)
        reversals = await self._reversals_for_date(d)
        net = collected - reversals

        expected_count = expected["finance_count"] + expected["chitti_count"]
        pending = max(expected["total"] - net, Decimal("0"))

        collection_rate = (
            (net / expected["total"] * Decimal("100")).quantize(Decimal("0.1"))
            if expected["total"] > 0
            else Decimal("0")
        )

        return {
            "date": str(d),
            "expected_total": expected["total"],
            "expected_count": expected_count,
            "finance_expected": expected["finance_total"],
            "chitti_expected": expected["chitti_total"],
            "collected_total": collected,
            "reversals_total": reversals,
            "net_collections": net,
            "pending_total": pending,
            "collection_rate": float(collection_rate),
        }

    # ===========================================================================
    # Detailed daily report (metrics + by-user + pending + recent)
    # ===========================================================================

    async def get_daily_report(self, report_date: Optional[date] = None) -> dict:
        """Full daily report: headline metrics, per-collector breakdown,
        pending (due but unpaid) items, and the day's payments."""
        d = report_date or today_ist()

        summary = await self.get_daily_summary(d)
        by_user = await self.collections_by_user(d)
        pending = await self.get_pending_details(d)
        payments = await self.get_day_payments(d)
        by_method = await self.collections_by_method(d)

        return {
            **summary,
            "by_user": by_user,
            "by_method": by_method,
            "pending_details": pending,
            "payments": payments,
        }

    # ===========================================================================
    # Collections grouped by collector (user)
    # ===========================================================================

    async def collections_by_user(self, report_date: Optional[date] = None) -> list[dict]:
        """Collections for the day grouped by the collector (user) who recorded them."""
        d = report_date or today_ist()

        result = await self.session.execute(
            select(
                PaymentTransaction.collected_by,
                func.coalesce(func.sum(PaymentTransaction.amount), Decimal("0")).label("total"),
                func.count(PaymentTransaction.id).label("count"),
                User.full_name,
                User.username,
                User.role,
            )
            .outerjoin(User, User.id == PaymentTransaction.collected_by)
            .where(
                PaymentTransaction.payment_date == d,
                PaymentTransaction.status == "COMPLETED",
                PaymentTransaction.is_reversal == False,  # noqa: E712
            )
            .group_by(PaymentTransaction.collected_by, User.full_name, User.username, User.role)
            .order_by(func.sum(PaymentTransaction.amount).desc())
        )
        rows = result.all()

        return [
            {
                "user_id": str(r.collected_by) if r.collected_by else None,
                "full_name": r.full_name or "Unknown",
                "username": r.username or "—",
                "role": r.role or "—",
                "collected_total": r.total,
                "payment_count": r.count,
            }
            for r in rows
        ]

    # ===========================================================================
    # Collections grouped by payment method
    # ===========================================================================

    async def collections_by_method(self, report_date: Optional[date] = None) -> list[dict]:
        d = report_date or today_ist()
        result = await self.session.execute(
            select(
                PaymentTransaction.payment_method,
                func.coalesce(func.sum(PaymentTransaction.amount), Decimal("0")).label("total"),
                func.count(PaymentTransaction.id).label("count"),
            )
            .where(
                PaymentTransaction.payment_date == d,
                PaymentTransaction.status == "COMPLETED",
                PaymentTransaction.is_reversal == False,  # noqa: E712
            )
            .group_by(PaymentTransaction.payment_method)
            .order_by(func.sum(PaymentTransaction.amount).desc())
        )
        return [
            {
                "method": r.payment_method,
                "total": r.total,
                "count": r.count,
            }
            for r in result.all()
        ]

    # ===========================================================================
    # Pending details (due that day, not fully collected)
    # ===========================================================================

    async def get_pending_details(self, report_date: Optional[date] = None) -> list[dict]:
        """Every finance installment + chitti period due on the day that is not
        fully paid, with the owning customer attached. This powers the
        'pending when clicked' drill-down."""
        d = report_date or today_ist()
        items: list[dict] = []

        # ---- Finance installments due on the day ----
        from app.models.finance import FinanceAccount

        fin_rows = await self.session.execute(
            select(
                FinanceSchedule.id,
                FinanceSchedule.installment_number,
                FinanceSchedule.expected_amount,
                FinanceSchedule.paid_amount,
                FinanceSchedule.remaining_amount,
                FinanceSchedule.status,
                FinanceAccount.account_number,
                Customer.id.label("customer_id"),
                Customer.full_name,
                Customer.mobile_number,
                Customer.customer_code,
            )
            .join(FinanceAccount, FinanceAccount.id == FinanceSchedule.finance_account_id)
            .join(Customer, Customer.id == FinanceAccount.customer_id)
            .where(FinanceSchedule.due_date == d)
        )
        for r in fin_rows.all():
            if r.status in ("CANCELLED",):
                continue
            items.append({
                "source": "FINANCE",
                "reference_id": str(r.id),
                "account_number": r.account_number,
                "customer_id": str(r.customer_id),
                "customer_name": r.full_name,
                "customer_code": r.customer_code,
                "mobile_number": r.mobile_number,
                "period_label": f"Installment {r.installment_number}",
                "expected": r.expected_amount,
                "paid": r.paid_amount,
                "pending": r.remaining_amount if r.remaining_amount > 0 else Decimal("0"),
                "status": r.status,
            })

        # ---- Chitti periods due on the day ----
        chitti_rows = await self.session.execute(
            select(ChittiPeriodSchedule).where(ChittiPeriodSchedule.due_date == d)
        )
        for sched in chitti_rows.scalars().all():
            if sched.pending_collection <= 0:
                continue
            chitti = await self._get_chitti_customer_group(sched.chitti_id)
            items.append({
                "source": "CHITTI",
                "reference_id": str(sched.id),
                "account_number": chitti.get("chitti_code"),
                "customer_id": None,
                "customer_name": chitti.get("name"),
                "customer_code": None,
                "mobile_number": None,
                "period_label": f"Period {sched.period_number}",
                "expected": sched.expected_collection,
                "paid": sched.actual_collection,
                "pending": sched.pending_collection,
                "status": sched.status,
            })

        return items

    # ===========================================================================
    # Payments recorded on the day (with collector + customer names)
    # ===========================================================================

    async def get_day_payments(self, report_date: Optional[date] = None) -> list[dict]:
        d = report_date or today_ist()
        result = await self.session.execute(
            select(
                PaymentTransaction,
                Customer.full_name.label("customer_name"),
                Customer.customer_code,
                User.full_name.label("collector_name"),
            )
            .outerjoin(Customer, Customer.id == PaymentTransaction.customer_id)
            .outerjoin(User, User.id == PaymentTransaction.collected_by)
            .where(PaymentTransaction.payment_date == d)
            .order_by(PaymentTransaction.created_at.desc())
        )
        return [
            {
                "id": str(p.PaymentTransaction.id),
                "transaction_id": p.PaymentTransaction.transaction_id,
                "customer_name": p.customer_name or "—",
                "customer_code": p.customer_code,
                "collector_name": p.collector_name or "—",
                "amount": p.PaymentTransaction.amount,
                "payment_method": p.PaymentTransaction.payment_method,
                "status": p.PaymentTransaction.status,
                "is_reversal": p.PaymentTransaction.is_reversal,
                "source": (
                    "CHITTI" if p.PaymentTransaction.chitti_account_id
                    else "FINANCE" if p.PaymentTransaction.finance_account_id
                    else "OTHER"
                ),
            }
            for p in result.all()
        ]

    # ===========================================================================
    # Plan-specific metrics (for the Chitti plan detail page)
    # ===========================================================================

    async def get_chitti_plan_metrics(self, plan_id: UUID) -> dict:
        """Aggregate metrics for every running/finished chitti spawned from a plan."""
        from app.models.chitti import Chitti, ChittiMember

        # All chittis for this plan
        chitti_rows = await self.session.execute(
            select(Chitti).where(Chitti.plan_id == plan_id)
        )
        chittis = list(chitti_rows.scalars().all())
        if not chittis:
            return {
                "plan_id": str(plan_id),
                "total_chittis": 0,
                "active_chittis": 0,
                "completed_chittis": 0,
                "total_members": 0,
                "total_expected": Decimal("0"),
                "total_collected": Decimal("0"),
                "total_pending": Decimal("0"),
                "total_payouts": Decimal("0"),
                "collection_rate": 0.0,
                "by_status": {},
            }

        chitti_ids = [c.id for c in chittis]

        # Count by status
        by_status: dict[str, int] = {}
        for c in chittis:
            by_status[c.status] = by_status.get(c.status, 0) + 1

        active = by_status.get("RUNNING", 0) + by_status.get("PAUSED", 0) + by_status.get("UPCOMING", 0)
        completed = by_status.get("COMPLETED", 0)

        # Member count
        member_count = await self.session.execute(
            select(func.count(ChittiMember.id)).where(ChittiMember.chitti_id.in_(chitti_ids))
        )
        total_members = member_count.scalar() or 0

        # Schedule aggregates
        sched_agg = await self.session.execute(
            select(
                func.coalesce(func.sum(ChittiPeriodSchedule.expected_collection), Decimal("0")),
                func.coalesce(func.sum(ChittiPeriodSchedule.actual_collection), Decimal("0")),
                func.coalesce(func.sum(ChittiPeriodSchedule.pending_collection), Decimal("0")),
            ).where(ChittiPeriodSchedule.chitti_id.in_(chitti_ids))
        )
        expected, collected, pending = sched_agg.one()

        # Payouts total
        from app.models.chitti import ChittiPayout

        payout_agg = await self.session.execute(
            select(
                func.coalesce(func.sum(ChittiPayout.net_payout), Decimal("0"))
            ).where(
                ChittiPayout.chitti_id.in_(chitti_ids),
                ChittiPayout.status == "PAID",
            )
        )
        total_payouts = payout_agg.scalar() or Decimal("0")

        collection_rate = (
            float((collected / expected * Decimal("100")).quantize(Decimal("0.1")))
            if expected > 0 else 0.0
        )

        return {
            "plan_id": str(plan_id),
            "total_chittis": len(chittis),
            "active_chittis": active,
            "completed_chittis": completed,
            "total_members": total_members,
            "total_expected": expected,
            "total_collected": collected,
            "total_pending": pending,
            "total_payouts": total_payouts,
            "collection_rate": collection_rate,
            "by_status": by_status,
        }

    # ===========================================================================
    # Helpers
    # ===========================================================================

    async def _expected_for_date(self, d: date) -> dict:
        """Sum of amounts due on a date across finance + chitti schedules."""
        # Finance installments due on the day (exclude cancelled)
        fin = await self.session.execute(
            select(
                func.coalesce(func.sum(FinanceSchedule.expected_amount), Decimal("0")),
                func.count(FinanceSchedule.id),
            ).where(
                FinanceSchedule.due_date == d,
                FinanceSchedule.status != "CANCELLED",
            )
        )
        finance_total, finance_count = fin.one()

        # Chitti periods due on the day
        chit = await self.session.execute(
            select(
                func.coalesce(func.sum(ChittiPeriodSchedule.expected_collection), Decimal("0")),
                func.count(ChittiPeriodSchedule.id),
            ).where(ChittiPeriodSchedule.due_date == d)
        )
        chitti_total, chitti_count = chit.one()

        return {
            "finance_total": finance_total,
            "finance_count": finance_count,
            "chitti_total": chitti_total,
            "chitti_count": chitti_count,
            "total": finance_total + chitti_total,
        }

    async def _collected_for_date(self, d: date) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(PaymentTransaction.amount), Decimal("0"))).where(
                PaymentTransaction.payment_date == d,
                PaymentTransaction.status == "COMPLETED",
                PaymentTransaction.is_reversal == False,  # noqa: E712
            )
        )
        return result.scalar() or Decimal("0")

    async def _reversals_for_date(self, d: date) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(PaymentTransaction.amount), Decimal("0"))).where(
                PaymentTransaction.payment_date == d,
                PaymentTransaction.status == "COMPLETED",
                PaymentTransaction.is_reversal == True,  # noqa: E712
            )
        )
        return result.scalar() or Decimal("0")

    async def _get_chitti_customer_group(self, chitti_id: UUID) -> dict:
        from app.models.chitti import Chitti

        result = await self.session.execute(
            select(Chitti).where(Chitti.id == chitti_id)
        )
        chitti = result.scalar_one_or_none()
        if not chitti:
            return {}
        return {"name": chitti.name, "chitti_code": chitti.chitti_code}
