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

from sqlalchemy import Date, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chitti import (
    Chitti,
    ChittiMember,
    ChittiMemberContribution,
    ChittiPeriodSchedule,
    ChittiTransaction,
)
from app.models.customer import Customer
from app.models.finance import FinanceSchedule
from app.models.payment import PaymentTransaction
from app.models.user import User
from app.utils.timezone import today_ist


def present(value):
    """Decimal -> float at the JSON boundary.

    All money is Decimal internally; the API contract (and the web client's
    types) says numbers, so decimals are converted once, here, instead of
    silently serialising as strings.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: present(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [present(item) for item in value]
    return value


# Chitti dues only exist once a chitti is running (or finished). DRAFT and
# CANCELLED chittis keep schedule rows from the plan preview; counting those as
# "due today" inflated the dashboard and disagreed with Chitti analytics.
FINANCIAL_CHITTI_STATUSES = ("RUNNING", "PAUSED", "COMPLETED")


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
        money = await self._collections_for_date(d)
        pending = await self._pending_for_date(d)

        finance_collected = money["finance_collected"]
        chitti_collected = money["chitti_collected"]
        finance_reversals = money["finance_reversals"]
        chitti_reversals = money["chitti_reversals"]

        # Finance and chitti money live in different ledgers; both are real
        # collections and they are reported together but never mixed up.
        collected = finance_collected + chitti_collected
        reversals = finance_reversals + chitti_reversals
        net = collected - reversals

        expected_count = expected["finance_count"] + expected["chitti_count"]

        collection_rate = (
            (net / expected["total"] * Decimal("100")).quantize(Decimal("0.1"))
            if expected["total"] > 0
            else Decimal("0")
        )

        return present({
            "date": str(d),
            "expected_total": expected["total"],
            "expected_count": expected_count,
            "finance_expected": expected["finance_total"],
            "chitti_expected": expected["chitti_total"],
            "collected_total": collected,
            "finance_collected": finance_collected,
            "chitti_collected": chitti_collected,
            "reversals_total": reversals,
            "finance_reversals": finance_reversals,
            "chitti_reversals": chitti_reversals,
            "net_collections": net,
            "finance_net": finance_collected - finance_reversals,
            "chitti_net": chitti_collected - chitti_reversals,
            # Pending is what is still unpaid on the day's dues, read from the
            # schedules themselves. expected - collected was wrong whenever a
            # payment landed on a different instalment than the one due.
            "pending_total": pending["total"],
            "finance_pending": pending["finance"],
            "chitti_pending": pending["chitti"],
            "collection_rate": float(collection_rate),
        })

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

        return present({
            **summary,
            "by_user": by_user,
            "by_method": by_method,
            "pending_details": pending,
            "payments": payments,
        })

    # ===========================================================================
    # Collections grouped by collector (user)
    # ===========================================================================

    async def collections_by_user(self, report_date: Optional[date] = None) -> list[dict]:
        """Collections for the day grouped by the collector (user) who recorded them."""
        d = report_date or today_ist()
        buckets: dict = {}

        def bucket(user_id, full_name, username, role) -> dict:
            key = str(user_id) if user_id else "unknown"
            entry = buckets.setdefault(
                key,
                {
                    "user_id": str(user_id) if user_id else None,
                    "full_name": full_name or "Unknown",
                    "username": username or "—",
                    "role": role or "—",
                    "finance_collected": Decimal("0"),
                    "chitti_collected": Decimal("0"),
                    "collected_total": Decimal("0"),
                    "payment_count": 0,
                },
            )
            return entry

        fin = await self.session.execute(
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
        )
        for r in fin.all():
            entry = bucket(r.collected_by, r.full_name, r.username, r.role)
            entry["finance_collected"] += r.total
            entry["collected_total"] += r.total
            entry["payment_count"] += r.count

        chit = await self.session.execute(
            select(
                ChittiTransaction.created_by,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ChittiTransaction.transaction_type == "CONTRIBUTION",
                                ChittiTransaction.amount,
                            ),
                            else_=-ChittiTransaction.amount,
                        )
                    ),
                    Decimal("0"),
                ).label("total"),
                func.count(ChittiTransaction.id).label("count"),
                User.full_name,
                User.username,
                User.role,
            )
            .outerjoin(User, User.id == ChittiTransaction.created_by)
            .where(self._chitti_business_date() == d)
            .group_by(ChittiTransaction.created_by, User.full_name, User.username, User.role)
        )
        for r in chit.all():
            entry = bucket(r.created_by, r.full_name, r.username, r.role)
            entry["chitti_collected"] += r.total
            entry["collected_total"] += r.total
            entry["payment_count"] += r.count

        rows = list(buckets.values())
        rows.sort(key=lambda x: x["collected_total"], reverse=True)
        return rows

    # ===========================================================================
    # Collections grouped by payment method
    # ===========================================================================

    async def collections_by_method(self, report_date: Optional[date] = None) -> list[dict]:
        d = report_date or today_ist()
        buckets: dict = {}

        def bucket(method) -> dict:
            mode = method or "OTHER"
            return buckets.setdefault(
                mode,
                {
                    "method": mode,
                    "finance_total": Decimal("0"),
                    "chitti_total": Decimal("0"),
                    "total": Decimal("0"),
                    "count": 0,
                },
            )

        fin = await self.session.execute(
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
        )
        for r in fin.all():
            entry = bucket(r.payment_method)
            entry["finance_total"] += r.total
            entry["total"] += r.total
            entry["count"] += r.count

        chit = await self.session.execute(
            select(
                ChittiTransaction.payment_method,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ChittiTransaction.transaction_type == "CONTRIBUTION",
                                ChittiTransaction.amount,
                            ),
                            else_=-ChittiTransaction.amount,
                        )
                    ),
                    Decimal("0"),
                ).label("total"),
                func.count(ChittiTransaction.id).label("count"),
            )
            .where(self._chitti_business_date() == d)
            .group_by(ChittiTransaction.payment_method)
        )
        for r in chit.all():
            entry = bucket(r.payment_method)
            entry["chitti_total"] += r.total
            entry["total"] += r.total
            entry["count"] += r.count

        rows = [row for row in buckets.values() if row["count"] > 0]
        rows.sort(key=lambda x: x["total"], reverse=True)
        return rows

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
            .where(
                FinanceSchedule.due_date == d,
                FinanceSchedule.remaining_amount > 0,
            )
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

        # ---- Chitti contributions due on the day (member level) ----
        # A period schedule only carries aggregates; the drill-down must name the
        # member who still owes money, otherwise it cannot be acted on.
        chitti_rows = await self.session.execute(
            select(
                ChittiMemberContribution,
                Chitti.chitti_code,
                Chitti.name.label("chitti_name"),
                ChittiMember.member_number,
                Customer.id.label("customer_id"),
                Customer.full_name,
                Customer.customer_code,
                Customer.mobile_number,
            )
            .join(
                ChittiPeriodSchedule,
                and_(
                    ChittiPeriodSchedule.chitti_id == ChittiMemberContribution.chitti_id,
                    ChittiPeriodSchedule.period_number
                    == ChittiMemberContribution.period_number,
                ),
            )
            .join(Chitti, Chitti.id == ChittiMemberContribution.chitti_id)
            .join(ChittiMember, ChittiMember.id == ChittiMemberContribution.member_id)
            .join(Customer, Customer.id == ChittiMember.customer_id)
            .where(
                ChittiPeriodSchedule.due_date == d,
                ChittiMemberContribution.remaining_amount > 0,
                Chitti.status.in_(FINANCIAL_CHITTI_STATUSES),
            )
        )
        for r in chitti_rows.all():
            con = r.ChittiMemberContribution
            items.append({
                "source": "CHITTI",
                "reference_id": str(con.id),
                "account_number": r.chitti_code,
                "customer_id": str(r.customer_id),
                "customer_name": r.full_name,
                "customer_code": r.customer_code,
                "mobile_number": r.mobile_number,
                "period_label": f"Period {con.period_number}",
                "chitti_name": r.chitti_name,
                "member_number": r.member_number,
                "expected": con.expected_amount,
                "paid": con.paid_amount,
                "pending": con.remaining_amount,
                "status": con.status,
            })

        return items

    # ===========================================================================
    # Payments recorded on the day (with collector + customer names)
    # ===========================================================================

    async def get_day_payments(self, report_date: Optional[date] = None) -> list[dict]:
        """Every payment recorded on the day, from both money streams."""
        d = report_date or today_ist()
        merged: list[tuple] = []

        fin = await self.session.execute(
            select(
                PaymentTransaction,
                Customer.full_name.label("customer_name"),
                Customer.customer_code,
                User.full_name.label("collector_name"),
            )
            .outerjoin(Customer, Customer.id == PaymentTransaction.customer_id)
            .outerjoin(User, User.id == PaymentTransaction.collected_by)
            .where(PaymentTransaction.payment_date == d)
        )
        for p in fin.all():
            txn = p.PaymentTransaction
            merged.append((
                txn.created_at,
                {
                    "id": str(txn.id),
                    "transaction_id": txn.transaction_id,
                    "customer_name": p.customer_name or "—",
                    "customer_code": p.customer_code,
                    "collector_name": p.collector_name or "—",
                    "amount": txn.amount,
                    "payment_method": txn.payment_method,
                    "status": txn.status,
                    "is_reversal": txn.is_reversal,
                    "source": (
                        "CHITTI" if txn.chitti_account_id
                        else "FINANCE" if txn.finance_account_id
                        else "OTHER"
                    ),
                },
            ))

        chit = await self.session.execute(
            select(
                ChittiTransaction,
                Customer.full_name.label("customer_name"),
                Customer.customer_code,
                User.full_name.label("collector_name"),
            )
            .outerjoin(ChittiMember, ChittiMember.id == ChittiTransaction.member_id)
            .outerjoin(Customer, Customer.id == ChittiMember.customer_id)
            .outerjoin(User, User.id == ChittiTransaction.created_by)
            .where(self._chitti_business_date() == d)
        )
        for row in chit.all():
            txn = row.ChittiTransaction
            merged.append((
                txn.created_at,
                {
                    "id": str(txn.id),
                    "transaction_id": f"CTX-{str(txn.id).split('-')[0].upper()}",
                    "customer_name": row.customer_name or "—",
                    "customer_code": row.customer_code,
                    "collector_name": row.collector_name or "—",
                    "amount": txn.amount,
                    "payment_method": txn.payment_method or "OTHER",
                    "status": (
                        "REVERSED" if txn.transaction_type == "REVERSAL" else "COMPLETED"
                    ),
                    "is_reversal": txn.transaction_type == "REVERSAL",
                    "source": "CHITTI",
                },
            ))

        merged.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in merged]

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
            select(func.count(ChittiMember.id)).where(
                ChittiMember.chitti_id.in_(chitti_ids),
                ChittiMember.status.notin_(("CANCELLED", "REJECTED", "LEFT")),
            )
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
        """Amounts due on a date: finance installments + running chitti periods."""
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

        chit = await self.session.execute(
            select(
                func.coalesce(func.sum(ChittiPeriodSchedule.expected_collection), Decimal("0")),
                func.count(ChittiPeriodSchedule.id),
            )
            .join(Chitti, Chitti.id == ChittiPeriodSchedule.chitti_id)
            .where(
                ChittiPeriodSchedule.due_date == d,
                Chitti.status.in_(FINANCIAL_CHITTI_STATUSES),
            )
        )
        chitti_total, chitti_count = chit.one()

        return {
            "finance_total": finance_total,
            "finance_count": finance_count,
            "chitti_total": chitti_total,
            "chitti_count": chitti_count,
            "total": finance_total + chitti_total,
        }

    async def _collections_for_date(self, d: date) -> dict:
        """Money actually collected on a date, kept separate per stream.

        Finance collections live only in `payment_transactions`; chitti
        contributions live only in `chitti_transactions`. Reading a single
        ledger is what made the dashboard disagree with Chitti analytics.
        """
        fin = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    PaymentTransaction.is_reversal.is_(False),
                                    PaymentTransaction.status == "COMPLETED",
                                ),
                                PaymentTransaction.amount,
                            ),
                            else_=Decimal("0"),
                        )
                    ),
                    Decimal("0"),
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                PaymentTransaction.is_reversal.is_(True),
                                PaymentTransaction.amount,
                            ),
                            else_=Decimal("0"),
                        )
                    ),
                    Decimal("0"),
                ),
            ).where(PaymentTransaction.payment_date == d)
        )
        finance_collected, finance_reversals = fin.one()

        chit = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ChittiTransaction.transaction_type == "CONTRIBUTION",
                                ChittiTransaction.amount,
                            ),
                            else_=Decimal("0"),
                        )
                    ),
                    Decimal("0"),
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ChittiTransaction.transaction_type == "REVERSAL",
                                ChittiTransaction.amount,
                            ),
                            else_=Decimal("0"),
                        )
                    ),
                    Decimal("0"),
                ),
            ).where(self._chitti_business_date() == d)
        )
        chitti_collected, chitti_reversals = chit.one()

        return {
            "finance_collected": finance_collected,
            "chitti_collected": chitti_collected,
            "finance_reversals": finance_reversals,
            "chitti_reversals": chitti_reversals,
        }

    async def _pending_for_date(self, d: date) -> dict:
        """Amount still unpaid on the dues of a date, per stream."""
        fin = await self.session.execute(
            select(
                func.coalesce(func.sum(FinanceSchedule.remaining_amount), Decimal("0"))
            ).where(
                FinanceSchedule.due_date == d,
                FinanceSchedule.status != "CANCELLED",
                FinanceSchedule.remaining_amount > 0,
            )
        )
        finance_pending = fin.scalar() or Decimal("0")

        chit = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(ChittiPeriodSchedule.pending_collection), Decimal("0")
                )
            )
            .join(Chitti, Chitti.id == ChittiPeriodSchedule.chitti_id)
            .where(
                ChittiPeriodSchedule.due_date == d,
                ChittiPeriodSchedule.pending_collection > 0,
                Chitti.status.in_(FINANCIAL_CHITTI_STATUSES),
            )
        )
        chitti_pending = chit.scalar() or Decimal("0")

        return {
            "finance": finance_pending,
            "chitti": chitti_pending,
            "total": finance_pending + chitti_pending,
        }

    @staticmethod
    def _chitti_business_date():
        """Business (IST) date a chitti transaction belongs to.

        An explicit payment_date always wins; legacy rows without one fall back
        to the insertion timestamp converted to IST (not UTC, which would move
        late-evening collections into the next day).
        """
        return func.coalesce(
            ChittiTransaction.payment_date,
            cast(func.timezone("Asia/Kolkata", ChittiTransaction.created_at), Date),
        )

    async def _get_chitti_customer_group(self, chitti_id: UUID) -> dict:
        from app.models.chitti import Chitti

        result = await self.session.execute(
            select(Chitti).where(Chitti.id == chitti_id)
        )
        chitti = result.scalar_one_or_none()
        if not chitti:
            return {}
        return {"name": chitti.name, "chitti_code": chitti.chitti_code}
