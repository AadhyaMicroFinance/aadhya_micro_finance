"""
Chitti analytics service — single source of truth for the Chitti control centre.

Money flows are read from the immutable chitti ledger (`chitti_transactions`):
  CONTRIBUTION increases money received, REVERSAL decreases it.

Expected / pending / overdue come from `chitti_period_schedule` (period level,
carries due dates) and `chitti_member_contributions` (member level, tracks
partial payments).  Nothing here is hardcoded — every figure is aggregated from
those tables.

All arithmetic is Decimal; values are converted to float only when building the
response payload (presentation boundary).
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chitti import (
    Chitti,
    ChittiMember,
    ChittiMemberContribution,
    ChittiPeriodSchedule,
    ChittiPlan,
    ChittiTransaction,
)
from app.models.customer import Customer
from app.models.user import User
from app.utils.timezone import from_utc, today_ist

ZERO = Decimal("0")
CONTRIBUTION_TYPES = ("CONTRIBUTION", "REVERSAL")
METHODS = ("CASH", "UPI", "BANK_TRANSFER", "OTHER")


def _f(value) -> float:
    """Decimal -> float for the JSON/presentation boundary."""
    if value is None:
        return 0.0
    return float(value)


def _ist_date(dt) -> date:
    return from_utc(dt).date()


def _txn_date(txn) -> date:
    """Business (IST) date the money was received.

    An explicitly recorded payment date wins over the insertion timestamp, so
    back-dated cash entries are reported in the period they were collected.
    """
    paid_on = getattr(txn, "payment_date", None)
    return paid_on if paid_on else _ist_date(txn.created_at)


def _pct(numerator: Decimal, denominator: Decimal) -> float:
    if not denominator or denominator <= ZERO:
        return 0.0
    return round(float(numerator / denominator) * 100, 1)


class ChittiAnalyticsService:
    """Business logic for the Chitti metrics & analytics dashboard."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================================
    # Overview (KPIs + every chart + tables)
    # =========================================================================

    async def get_overview(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        chitti_id: Optional[UUID] = None,
        member_id: Optional[UUID] = None,
        payment_mode: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict:
        today = today_ist()
        end = end_date or today
        start = start_date or end.replace(day=1)
        if start > end:
            start, end = end, start

        chittis = await self._load_chittis(chitti_id)
        if not chittis:
            return self._empty_overview(start, end)

        chitti_ids = [c.id for c in chittis]
        plan_names = await self._load_plan_names(chittis)

        members, customers = await self._load_members(chitti_ids, member_id)
        member_by_id = {m.id: m for m in members}
        schedules = await self._load_schedules(chitti_ids)
        contributions = await self._load_contributions(chitti_ids, member_id)
        ledger = await self._load_ledger(chitti_ids, member_id, payment_mode)
        user_names = await self._load_user_names({t.created_by for t in ledger})

        # ---- date windows ----
        range_txns = [t for t in ledger if start <= _txn_date(t) <= end]
        today_txns = [t for t in ledger if _txn_date(t) == today]
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=(end - start).days)
        prev_txns = [t for t in ledger if prev_start <= _txn_date(t) <= prev_end]

        collected_range = self._ledger_total(range_txns)
        collected_today = self._ledger_total(today_txns)
        collected_prev = self._ledger_total(prev_txns)
        collected_lifetime = self._ledger_total(ledger)

        # DRAFT/CANCELLED chittis have schedules but nothing is actually due yet,
        # so they must not inflate expected / pending / overdue totals.
        financial_ids = {c.id for c in chittis if c.status not in ("DRAFT", "CANCELLED")}
        fin_schedules = [s for s in schedules if s.chitti_id in financial_ids]

        expected_range = sum(
            (s.expected_collection for s in fin_schedules if start <= s.due_date <= end),
            ZERO,
        )
        expected_today = sum(
            (s.expected_collection for s in fin_schedules if s.due_date == today), ZERO
        )

        total_expected = sum((s.expected_collection for s in fin_schedules), ZERO)
        total_actual = sum((s.actual_collection for s in fin_schedules), ZERO)
        total_pending = sum(
            (max(s.expected_collection - s.actual_collection, ZERO) for s in fin_schedules),
            ZERO,
        )
        overdue_amount = sum(
            (
                max(s.expected_collection - s.actual_collection, ZERO)
                for s in fin_schedules
                if s.due_date < today
            ),
            ZERO,
        )
        total_value = sum((c.total_value for c in chittis), ZERO)

        active_chittis = [c for c in chittis if c.status == "RUNNING"]
        completed_chittis = [c for c in chittis if c.status == "COMPLETED"]
        active_members = [m for m in members if m.status == "ACTIVE"]

        # ---- member-level rows (derived from contributions + schedule dates) ----
        schedule_by_key = {(s.chitti_id, s.period_number): s for s in schedules}
        contribution_rows = []
        for con in contributions:
            sched = schedule_by_key.get((con.chitti_id, con.period_number))
            due = sched.due_date if sched else None
            contribution_rows.append(
                {
                    "contribution": con,
                    "due_date": due,
                    "state": self._contribution_state(con, due, today),
                }
            )

        member_rows = self._build_member_rows(
            members, customers, contributions, schedule_by_key, ledger, today
        )
        chitti_name_map = {c.id: c.name for c in chittis}
        for row in member_rows:
            row["chitti_name"] = chitti_name_map.get(UUID(row["chitti_id"]), "—")
        if status:
            wanted = status.upper()
            member_rows = [r for r in member_rows if r["status"] == wanted]

        pending_details = self._build_pending_details(
            contribution_rows, member_by_id, customers, chittis, ledger, today
        )

        # ---- series & distributions ----
        daily_series = self._daily_series(fin_schedules, ledger, start, end, today)
        monthly_series = self._monthly_series(fin_schedules, ledger, end)
        status_distribution = self._status_distribution(contribution_rows)
        mode_distribution = self._mode_distribution(range_txns)
        today_by_method = self._method_totals(today_txns)

        # ---- today's people counts ----
        paid_member_ids = {t.member_id for t in today_txns if t.member_id}
        due_today_members = {
            con.member_id
            for con, s in ((c, schedule_by_key.get((c.chitti_id, c.period_number))) for c in contributions)
            if s and s.due_date == today
        }
        partial_today = sum(
            1
            for row in contribution_rows
            if row["due_date"] == today
            and ZERO < row["contribution"].paid_amount < row["contribution"].expected_amount
        )
        overdue_contributions = sum(
            1
            for row in contribution_rows
            if row["state"] == "OVERDUE" and row["contribution"].remaining_amount > ZERO
        )

        monthly_collected = sum(
            (
                t.amount if t.transaction_type == "CONTRIBUTION" else -t.amount
                for t in ledger
                if _txn_date(t).month == today.month
                and _txn_date(t).year == today.year
            ),
            ZERO,
        )
        yearly_collected = sum(
            (
                t.amount if t.transaction_type == "CONTRIBUTION" else -t.amount
                for t in ledger
                if _txn_date(t).year == today.year
            ),
            ZERO,
        )
        refunds = sum(
            (t.amount for t in ledger if t.transaction_type == "REVERSAL"), ZERO
        )
        advance_total = sum(
            (
                max(row["contribution"].paid_amount - row["contribution"].expected_amount, ZERO)
                for row in contribution_rows
            ),
            ZERO,
        )

        # ---- chitti-wise metrics ----
        chitti_metrics = self._build_chitti_metrics(
            chittis, plan_names, members, schedules, ledger, today, month=today.month
        )
        if chitti_id:
            chitti_metrics = [m for m in chitti_metrics if m["id"] == str(chitti_id)]

        transactions = self._build_transactions(ledger, member_by_id, customers, chittis, user_names)
        transactions.reverse()  # newest first
        for txn in transactions:
            txn.pop("date_value", None)
            txn.pop("timestamp", None)

        return {
            "filters": {
                "start_date": str(start),
                "end_date": str(end),
                "chitti_id": str(chitti_id) if chitti_id else None,
                "member_id": str(member_id) if member_id else None,
                "payment_mode": payment_mode,
                "status": status,
            },
            "today": {
                "date": str(today),
                "expected": _f(expected_today),
                "collected": _f(collected_today),
                "pending": _f(max(expected_today - collected_today, ZERO)),
                "members_paid": len(paid_member_ids),
                "members_due": len(due_today_members),
                "members_unpaid": len(due_today_members - paid_member_ids),
                "partial_count": partial_today,
                "overdue_count": overdue_contributions,
                "payments_count": len(today_txns),
                "by_method": today_by_method,
            },
            "kpis": {
                "total_chittis": len(chittis),
                "active_chittis": len(active_chittis),
                "completed_chittis": len(completed_chittis),
                "total_chitti_value": _f(total_value),
                "total_expected": _f(total_expected),
                "total_collected": _f(collected_lifetime),
                "total_pending": _f(total_pending),
                "total_overdue": _f(overdue_amount),
                "total_members": len(active_members),
                "collection_efficiency": _pct(collected_lifetime, total_expected),
                "range_expected": _f(expected_range),
                "range_collected": _f(collected_range),
                "range_pending": _f(max(expected_range - collected_range, ZERO)),
                "today_expected": _f(expected_today),
                "today_collected": _f(collected_today),
                "today_pending": _f(max(expected_today - collected_today, ZERO)),
                "overdue_amount": _f(overdue_amount),
                "overdue_members": sum(
                    1 for r in member_rows if r["status"] == "OVERDUE"
                ),
                "comparison": {
                    "previous_collected": _f(collected_prev),
                    "change_amount": _f(collected_range - collected_prev),
                    "change_pct": _pct(collected_range - collected_prev, collected_prev),
                },
            },
            "daily": {
                "series": daily_series,
                "expected": _f(expected_range),
                "collected": _f(collected_range),
                "pending": _f(max(expected_range - collected_range, ZERO)),
                "by_method": self._method_totals(range_txns),
            },
            "monthly": {"series": monthly_series},
            "status_distribution": status_distribution,
            "mode_distribution": mode_distribution,
            "chitti_metrics": chitti_metrics,
            "member_rows": member_rows,
            "pending_details": pending_details,
            "transactions": transactions,
            "financial_summary": {
                "total_receivable": _f(total_expected),
                "total_received": _f(collected_lifetime),
                "total_outstanding": _f(total_pending),
                "total_overdue": _f(overdue_amount),
                "total_advance": _f(advance_total),
                "total_refunds": _f(refunds),
                "total_adjustments": 0.0,
                "daily_collection": _f(collected_today),
                "monthly_collection": _f(monthly_collected),
                "yearly_collection": _f(yearly_collected),
            },
        }

    # =========================================================================
    # Transaction ledger (paginated)
    # =========================================================================

    async def get_ledger(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        search: Optional[str] = None,
        chitti_id: Optional[UUID] = None,
        member_id: Optional[UUID] = None,
        payment_mode: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> tuple[list[dict], int]:
        chittis = await self._load_chittis(chitti_id)
        if not chittis:
            return [], 0
        chitti_ids = [c.id for c in chittis]
        members, customers = await self._load_members(chitti_ids, member_id)
        member_by_id = {m.id: m for m in members}
        ledger = await self._load_ledger(chitti_ids, member_id, payment_mode)
        user_names = await self._load_user_names({t.created_by for t in ledger})

        rows = self._build_transactions(
            ledger, member_by_id, customers, chittis, user_names
        )
        if start_date:
            rows = [r for r in rows if r["date_value"] >= start_date]
        if end_date:
            rows = [r for r in rows if r["date_value"] <= end_date]
        if search:
            needle = search.lower()
            rows = [
                r
                for r in rows
                if needle in (r["member_name"] or "").lower()
                or needle in (r["chitti_name"] or "").lower()
                or needle in (r["reference_number"] or "").lower()
                or needle in r["transaction_id"].lower()
            ]

        rows.sort(key=lambda r: r["timestamp"], reverse=True)
        total = len(rows)
        skip = (page - 1) * per_page
        sliced = rows[skip : skip + per_page]
        for r in sliced:
            r.pop("date_value", None)
            r.pop("timestamp", None)
        return sliced, total

    # =========================================================================
    # Loaders
    # =========================================================================

    async def _load_chittis(self, chitti_id: Optional[UUID]) -> list[Chitti]:
        stmt = select(Chitti).where(Chitti.status != "ARCHIVED")
        if chitti_id:
            stmt = stmt.where(Chitti.id == chitti_id)
        stmt = stmt.order_by(Chitti.created_at.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def _load_plan_names(self, chittis: Iterable[Chitti]) -> dict:
        plan_ids = {c.plan_id for c in chittis}
        if not plan_ids:
            return {}
        stmt = select(ChittiPlan.id, ChittiPlan.name).where(ChittiPlan.id.in_(plan_ids))
        return {row[0]: row[1] for row in (await self.session.execute(stmt)).all()}

    async def _load_members(self, chitti_ids: list[UUID], member_id: Optional[UUID]):
        stmt = (
            select(ChittiMember, Customer)
            .join(Customer, Customer.id == ChittiMember.customer_id)
            .where(ChittiMember.chitti_id.in_(chitti_ids))
            .where(ChittiMember.status.notin_(("CANCELLED", "REJECTED", "LEFT")))
            .order_by(ChittiMember.member_number.asc())
        )
        if member_id:
            stmt = stmt.where(ChittiMember.id == member_id)
        rows = (await self.session.execute(stmt)).all()
        members = [r[0] for r in rows]
        customers = {r[0].customer_id: r[1] for r in rows}
        return members, customers

    async def _load_schedules(self, chitti_ids: list[UUID]) -> list[ChittiPeriodSchedule]:
        stmt = (
            select(ChittiPeriodSchedule)
            .where(ChittiPeriodSchedule.chitti_id.in_(chitti_ids))
            .order_by(ChittiPeriodSchedule.due_date.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _load_contributions(
        self, chitti_ids: list[UUID], member_id: Optional[UUID]
    ) -> list[ChittiMemberContribution]:
        stmt = select(ChittiMemberContribution).where(
            ChittiMemberContribution.chitti_id.in_(chitti_ids)
        )
        if member_id:
            stmt = stmt.where(ChittiMemberContribution.member_id == member_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _load_ledger(
        self,
        chitti_ids: list[UUID],
        member_id: Optional[UUID] = None,
        payment_mode: Optional[str] = None,
    ) -> list[ChittiTransaction]:
        stmt = (
            select(ChittiTransaction)
            .where(ChittiTransaction.chitti_id.in_(chitti_ids))
            .where(ChittiTransaction.transaction_type.in_(CONTRIBUTION_TYPES))
            .order_by(ChittiTransaction.created_at.asc())
        )
        if member_id:
            stmt = stmt.where(ChittiTransaction.member_id == member_id)
        if payment_mode:
            stmt = stmt.where(ChittiTransaction.payment_method == payment_mode)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _load_user_names(self, user_ids: set) -> dict:
        ids = {uid for uid in user_ids if uid}
        if not ids:
            return {}
        stmt = select(User.id, User.full_name, User.username).where(User.id.in_(ids))
        return {row[0]: (row[1] or row[2]) for row in (await self.session.execute(stmt)).all()}

    # =========================================================================
    # Computation helpers
    # =========================================================================

    @staticmethod
    def _ledger_total(txns: Iterable[ChittiTransaction]) -> Decimal:
        total = ZERO
        for t in txns:
            total += t.amount if t.transaction_type == "CONTRIBUTION" else -t.amount
        return total

    @staticmethod
    def _contribution_state(
        con: ChittiMemberContribution, due_date: Optional[date], today: date
    ) -> str:
        paid = con.paid_amount
        expected = con.expected_amount
        remaining = max(expected - paid, ZERO)
        if paid >= expected and expected > ZERO:
            return "PAID"
        if paid > expected:
            return "ADVANCE_PAID"
        if due_date and due_date < today and remaining > ZERO:
            return "OVERDUE"
        if paid > ZERO and remaining > ZERO:
            return "PARTIALLY_PAID"
        return "PENDING"

    def _build_member_rows(
        self,
        members,
        customers,
        contributions,
        schedule_by_key,
        ledger,
        today: date,
    ) -> list[dict]:
        contribs_by_member: dict = {}
        for con in contributions:
            contribs_by_member.setdefault(con.member_id, []).append(con)

        last_payment: dict = {}
        paid_by_member: dict = {}
        for t in ledger:
            if not t.member_id:
                continue
            d = _txn_date(t)
            signed = t.amount if t.transaction_type == "CONTRIBUTION" else -t.amount
            prev = paid_by_member.get(t.member_id)
            if prev is None or d >= prev[0]:
                paid_by_member[t.member_id] = (d, t.payment_method, signed)
            if t.transaction_type == "CONTRIBUTION":
                if t.member_id not in last_payment or d >= last_payment[t.member_id]["date"]:
                    last_payment[t.member_id] = {
                        "date": d,
                        "mode": t.payment_method,
                        "amount": t.amount,
                    }

        rows = []
        for member in members:
            customer = customers.get(member.customer_id)
            cons = contribs_by_member.get(member.id, [])
            expected_total = sum((c.expected_amount for c in cons), ZERO)
            paid_total = sum((c.paid_amount for c in cons), ZERO)
            pending_total = sum((max(c.expected_amount - c.paid_amount, ZERO) for c in cons), ZERO)

            # Status must reflect what is due SO FAR — future installments are not
            # arrears, so they never make an up-to-date member "partially paid".
            overdue = ZERO
            due_expected = ZERO
            due_paid = ZERO
            due_pending = ZERO
            advance = ZERO
            for c in cons:
                sched = schedule_by_key.get((c.chitti_id, c.period_number))
                remaining = max(c.expected_amount - c.paid_amount, ZERO)
                advance += max(c.paid_amount - c.expected_amount, ZERO)
                if sched and sched.due_date <= today:
                    due_expected += c.expected_amount
                    due_paid += c.paid_amount
                    due_pending += remaining
                    if sched.due_date < today and remaining > ZERO:
                        overdue += remaining

            if due_pending <= ZERO and advance > ZERO:
                derived = "ADVANCE_PAID"
            elif due_pending <= ZERO and due_expected > ZERO:
                derived = "PAID"
            elif overdue > ZERO:
                derived = "OVERDUE"
            elif due_paid > ZERO:
                derived = "PARTIALLY_PAID"
            else:
                derived = "PENDING"

            last = last_payment.get(member.id)
            rows.append(
                {
                    "member_id": str(member.id),
                    "chitti_id": str(member.chitti_id),
                    "member_number": member.member_number,
                    "member_name": customer.full_name if customer else "—",
                    "customer_code": customer.customer_code if customer else None,
                    "mobile_number": customer.mobile_number if customer else None,
                    "chitti_name": None,  # filled by caller if needed
                    "expected_total": _f(expected_total),
                    "paid_total": _f(paid_total),
                    "pending_total": _f(pending_total),
                    "due_total": _f(due_expected),
                    "due_pending": _f(due_pending),
                    "advance_amount": _f(advance),
                    "overdue_amount": _f(overdue),
                    "status": derived,
                    "payment_date": str(last["date"]) if last else None,
                    "payment_mode": last["mode"] if last else None,
                    "last_payment_amount": _f(last["amount"]) if last else 0.0,
                }
            )
        return rows

    def _build_pending_details(
        self,
        contribution_rows,
        member_by_id,
        customers,
        chittis,
        ledger,
        today: date,
    ) -> list[dict]:
        chitti_names = {c.id: c.name for c in chittis}
        outstanding_by_member: dict = {}
        last_payment: dict = {}
        for t in ledger:
            if not t.member_id:
                continue
            d = _txn_date(t)
            if t.transaction_type == "CONTRIBUTION":
                if t.member_id not in last_payment or d > last_payment[t.member_id]:
                    last_payment[t.member_id] = d

        details = []
        for row in contribution_rows:
            con = row["contribution"]
            if con.remaining_amount <= ZERO:
                continue
            member = member_by_id.get(con.member_id)
            if not member:
                continue
            customer = customers.get(member.customer_id)
            due = row["due_date"]
            days_overdue = (today - due).days if due and due < today else 0
            details.append(
                {
                    "member_id": str(member.id),
                    "member_name": customer.full_name if customer else "—",
                    "mobile_number": customer.mobile_number if customer else None,
                    "chitti_id": str(con.chitti_id),
                    "chitti_name": chitti_names.get(con.chitti_id, "—"),
                    "period_number": con.period_number,
                    "due_date": str(due) if due else None,
                    "days_overdue": days_overdue,
                    "amount_pending": _f(con.remaining_amount),
                    "amount_expected": _f(con.expected_amount),
                    "amount_paid": _f(con.paid_amount),
                    "last_payment_date": str(last_payment[member.id]) if member.id in last_payment else None,
                    "total_outstanding": _f(
                        outstanding_by_member.setdefault(str(member.id), ZERO)
                    ),
                    "status": row["state"],
                }
            )

        # Fill total outstanding per member across all their contributions.
        totals: dict = {}
        for row in contribution_rows:
            con = row["contribution"]
            totals[con.member_id] = totals.get(con.member_id, ZERO) + con.remaining_amount
        for d in details:
            member_out = totals.get(UUID(d["member_id"]), ZERO)
            d["total_outstanding"] = _f(member_out)

        details.sort(key=lambda d: (-d["days_overdue"], d["due_date"] or ""))
        return details

    def _daily_series(self, schedules, ledger, start: date, end: date, today: date) -> list[dict]:
        span = (end - start).days
        if span > 120:
            start = end - timedelta(days=119)
            span = 119

        expected_by_date: dict = {}
        for s in schedules:
            expected_by_date[s.due_date] = expected_by_date.get(s.due_date, ZERO) + s.expected_collection

        collected_by_date: dict = {}
        for t in ledger:
            d = _txn_date(t)
            if not (start <= d <= end):
                continue
            collected_by_date[d] = collected_by_date.get(d, ZERO) + (
                t.amount if t.transaction_type == "CONTRIBUTION" else -t.amount
            )

        series = []
        for i in range(span + 1):
            d = start + timedelta(days=i)
            expected = expected_by_date.get(d, ZERO)
            collected = collected_by_date.get(d, ZERO)
            series.append(
                {
                    "date": str(d),
                    "expected": _f(expected),
                    "collected": _f(collected),
                    "pending": _f(max(expected - collected, ZERO)),
                }
            )
        return series

    def _monthly_series(self, schedules, ledger, end: date) -> list[dict]:
        months: list[tuple[int, int]] = []
        y, m = end.year, end.month
        for _ in range(6):
            months.append((y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        months.reverse()

        expected_by_month: dict = {}
        for s in schedules:
            key = (s.due_date.year, s.due_date.month)
            expected_by_month[key] = expected_by_month.get(key, ZERO) + s.expected_collection

        collected_by_month: dict = {}
        for t in ledger:
            d = _txn_date(t)
            key = (d.year, d.month)
            collected_by_month[key] = collected_by_month.get(key, ZERO) + (
                t.amount if t.transaction_type == "CONTRIBUTION" else -t.amount
            )

        out = []
        for key in months:
            out.append(
                {
                    "month": f"{key[0]}-{key[1]:02d}",
                    "label": date(key[0], key[1], 1).strftime("%b %Y"),
                    "expected": _f(expected_by_month.get(key, ZERO)),
                    "collected": _f(collected_by_month.get(key, ZERO)),
                }
            )
        return out

    @staticmethod
    def _status_distribution(contribution_rows) -> list[dict]:
        buckets: dict = {}
        for row in contribution_rows:
            state = row["state"]
            entry = buckets.setdefault(state, {"status": state, "count": 0, "amount": ZERO})
            entry["count"] += 1
            entry["amount"] += row["contribution"].expected_amount
        order = ["PAID", "PARTIALLY_PAID", "PENDING", "OVERDUE", "ADVANCE_PAID"]
        out = []
        for state in order:
            entry = buckets.get(state)
            if entry:
                out.append(
                    {"status": state, "count": entry["count"], "amount": _f(entry["amount"])}
                )
        for state, entry in buckets.items():
            if state not in order:
                out.append({"status": state, "count": entry["count"], "amount": _f(entry["amount"])})
        return out

    @staticmethod
    def _method_totals(txns) -> list[dict]:
        buckets = {m: {"mode": m, "amount": ZERO, "count": 0} for m in METHODS}
        for t in txns:
            mode = t.payment_method or "OTHER"
            entry = buckets.setdefault(mode, {"mode": mode, "amount": ZERO, "count": 0})
            entry["amount"] += t.amount if t.transaction_type == "CONTRIBUTION" else -t.amount
            entry["count"] += 1
        return [
            {"mode": e["mode"], "amount": _f(e["amount"]), "count": e["count"]}
            for e in buckets.values()
        ]

    @staticmethod
    def _mode_distribution(txns) -> list[dict]:
        return [m for m in ChittiAnalyticsService._method_totals(txns) if m["count"] > 0]

    def _build_chitti_metrics(
        self, chittis, plan_names, members, schedules, ledger, today: date, month: int
    ) -> list[dict]:
        members_by_chitti: dict = {}
        for m in members:
            members_by_chitti.setdefault(m.chitti_id, []).append(m)

        sched_by_chitti: dict = {}
        for s in schedules:
            sched_by_chitti.setdefault(s.chitti_id, []).append(s)

        collected_by_chitti: dict = {}
        today_by_chitti: dict = {}
        month_by_chitti: dict = {}
        for t in ledger:
            signed = t.amount if t.transaction_type == "CONTRIBUTION" else -t.amount
            collected_by_chitti[t.chitti_id] = collected_by_chitti.get(t.chitti_id, ZERO) + signed
            d = _txn_date(t)
            if d == today:
                today_by_chitti[t.chitti_id] = today_by_chitti.get(t.chitti_id, ZERO) + signed
            if d.year == today.year and d.month == month:
                month_by_chitti[t.chitti_id] = month_by_chitti.get(t.chitti_id, ZERO) + signed

        out = []
        for c in chittis:
            scheds = sched_by_chitti.get(c.id, [])
            expected = sum((s.expected_collection for s in scheds), ZERO)
            actual = sum((s.actual_collection for s in scheds), ZERO)
            pending = sum((max(s.expected_collection - s.actual_collection, ZERO) for s in scheds), ZERO)
            overdue = sum(
                (
                    max(s.expected_collection - s.actual_collection, ZERO)
                    for s in scheds
                    if s.due_date < today
                ),
                ZERO,
            )
            if c.status in ("DRAFT", "CANCELLED"):
                # Not running yet — past plan dates are not arrears.
                overdue = ZERO
            next_due = next(
                (s.due_date for s in scheds if s.due_date >= today and s.actual_collection < s.expected_collection),
                None,
            )
            chitti_members = members_by_chitti.get(c.id, [])
            out.append(
                {
                    "id": str(c.id),
                    "chitti_code": c.chitti_code,
                    "name": c.name,
                    "plan_name": plan_names.get(c.plan_id),
                    "status": c.status,
                    "branch": c.branch,
                    "start_date": str(c.start_date),
                    "end_date": str(c.end_date),
                    "total_value": _f(c.total_value),
                    "member_count": len(chitti_members),
                    "active_members": sum(1 for m in chitti_members if m.status == "ACTIVE"),
                    "expected": _f(expected),
                    "collected": _f(collected_by_chitti.get(c.id, ZERO)),
                    "pending": _f(pending),
                    "overdue": _f(overdue),
                    "today_collection": _f(today_by_chitti.get(c.id, ZERO)),
                    "month_collection": _f(month_by_chitti.get(c.id, ZERO)),
                    "remaining": _f(pending),
                    "collection_pct": _pct(actual or collected_by_chitti.get(c.id, ZERO), expected),
                    "next_due_date": str(next_due) if next_due else None,
                    "current_period": c.current_period,
                    "total_periods": (c.plan_snapshot or {}).get("duration", 0),
                }
            )
        out.sort(key=lambda m: m["collected"], reverse=True)
        return out

    def _build_transactions(self, ledger, member_by_id, customers, chittis, user_names) -> list[dict]:
        chitti_names = {c.id: c.name for c in chittis}
        rows = []
        for t in ledger:
            member = member_by_id.get(t.member_id) if t.member_id else None
            customer = customers.get(member.customer_id) if member else None
            ist_dt = from_utc(t.created_at)
            business_date = t.payment_date or ist_dt.date()
            rows.append(
                {
                    "id": str(t.id),
                    "transaction_id": f"CTX-{str(t.id).split('-')[0].upper()}",
                    "member_id": str(t.member_id) if t.member_id else None,
                    "member_name": customer.full_name if customer else "—",
                    "chitti_id": str(t.chitti_id),
                    "chitti_name": chitti_names.get(t.chitti_id, "—"),
                    "transaction_type": t.transaction_type,
                    "amount": _f(t.amount),
                    "payment_method": t.payment_method,
                    "reference_number": t.reference_number,
                    "period_number": t.period_number,
                    "received_by": user_names.get(t.created_by) if t.created_by else None,
                    "status": "REVERSED" if t.transaction_type == "REVERSAL" else "COMPLETED",
                    "remarks": t.notes,
                    "created_at": ist_dt.strftime("%Y-%m-%d %H:%M"),
                    "payment_date": str(business_date),
                    "date_value": business_date,
                    "timestamp": ist_dt,
                }
            )
        return rows

    # =========================================================================
    # Empty payload
    # =========================================================================

    def _empty_overview(self, start: date, end: date) -> dict:
        return {
            "filters": {
                "start_date": str(start),
                "end_date": str(end),
                "chitti_id": None,
                "member_id": None,
                "payment_mode": None,
                "status": None,
            },
            "today": {
                "date": str(today_ist()),
                "expected": 0.0,
                "collected": 0.0,
                "pending": 0.0,
                "members_paid": 0,
                "members_due": 0,
                "members_unpaid": 0,
                "partial_count": 0,
                "overdue_count": 0,
                "payments_count": 0,
                "by_method": [],
            },
            "kpis": {
                "total_chittis": 0,
                "active_chittis": 0,
                "completed_chittis": 0,
                "total_chitti_value": 0.0,
                "total_expected": 0.0,
                "total_collected": 0.0,
                "total_pending": 0.0,
                "total_overdue": 0.0,
                "total_members": 0,
                "collection_efficiency": 0.0,
                "range_expected": 0.0,
                "range_collected": 0.0,
                "range_pending": 0.0,
                "today_expected": 0.0,
                "today_collected": 0.0,
                "today_pending": 0.0,
                "overdue_amount": 0.0,
                "overdue_members": 0,
                "comparison": {"previous_collected": 0.0, "change_amount": 0.0, "change_pct": 0.0},
            },
            "daily": {"series": [], "expected": 0.0, "collected": 0.0, "pending": 0.0, "by_method": []},
            "monthly": {"series": []},
            "status_distribution": [],
            "mode_distribution": [],
            "chitti_metrics": [],
            "member_rows": [],
            "pending_details": [],
            "transactions": [],
            "financial_summary": {
                "total_receivable": 0.0,
                "total_received": 0.0,
                "total_outstanding": 0.0,
                "total_overdue": 0.0,
                "total_advance": 0.0,
                "total_refunds": 0.0,
                "total_adjustments": 0.0,
                "daily_collection": 0.0,
                "monthly_collection": 0.0,
                "yearly_collection": 0.0,
            },
        }
