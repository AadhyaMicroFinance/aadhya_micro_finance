"""
Seed realistic Chitti demo records so the analytics dashboard can be verified
against real database rows (not hardcoded metrics).

Creates two [Demo] chittis with members, period schedules, member contributions
and ledger transactions spread across recent weeks, then leaves the rest of the
database untouched.

Run inside the backend container:
    PYTHONPATH=/app python scripts/seed_chitti_analytics.py

Remove the demo rows again with:
    DELETE FROM chittis WHERE name LIKE '[Demo]%';   -- cascades to children
"""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from app.db.database import async_session_factory
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
from app.utils.timezone import today_ist

ZERO = Decimal("0")
METHOD_CYCLE = ("CASH", "UPI", "BANK_TRANSFER", "OTHER")
FREQUENCY_DAYS = {"DAILY": 1, "WEEKLY": 7, "BIWEEKLY": 14, "MONTHLY": 30}

# paid fractions: member index -> {period_number: fraction_of_installment_paid}
SCENARIOS = [
    {
        "code": "DEMO-0001",
        "name": "[Demo] Diwali Weekly Chitti",
        "start_offset_days": -28,
        "member_count": 4,
        "paid": {
            0: {1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
            1: {1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
            2: {1: 1, 2: 1, 3: 1, 4: 1, 5: 0.5},
            3: {1: 1, 2: 1, 3: 1},
        },
    },
    {
        "code": "DEMO-0002",
        "name": "[Demo] Festive Weekly Chitti",
        "start_offset_days": -14,
        "member_count": 3,
        "paid": {
            0: {1: 1, 2: 1, 3: 1},
            1: {1: 1, 2: 1},
            2: {1: 1, 2: 1, 3: 1},
        },
    },
]


async def _delete_demo(session) -> None:
    existing = (
        await session.execute(select(Chitti).where(Chitti.name.like("[Demo]%")))
    ).scalars().all()
    for chitti in existing:
        await session.delete(chitti)
    if existing:
        await session.flush()
        print(f"Removed {len(existing)} existing demo chitti(s).")


async def seed() -> None:
    today = today_ist()
    async with async_session_factory() as session:
        plan = (await session.execute(select(ChittiPlan).limit(1))).scalar_one_or_none()
        if not plan:
            print("No chitti plan found — create a plan first. Aborting.")
            return

        admin = (
            await session.execute(select(User).where(User.username == "admin"))
        ).scalar_one_or_none() or (await session.execute(select(User).limit(1))).scalar_one_or_none()

        customers = (
            await session.execute(select(Customer).order_by(Customer.customer_code))
        ).scalars().all()
        if not customers:
            print("No customers found — add customers first. Aborting.")
            return

        installment = Decimal(
            str(plan.contribution_rules.get("installment_amount") or 0)
        )
        if installment <= ZERO:
            installment = (plan.total_value / Decimal(plan.member_count)).quantize(Decimal("0.01"))

        duration = int(plan.duration)
        days_per_period = FREQUENCY_DAYS.get(plan.frequency, 7)
        total_value = plan.total_value

        await _delete_demo(session)

        created = []
        for scenario in SCENARIOS:
            member_count = min(scenario["member_count"], len(customers))
            if member_count == 0:
                continue
            start = today + timedelta(days=scenario["start_offset_days"])
            end = start + timedelta(days=days_per_period * duration)

            chitti = Chitti(
                chitti_code=scenario["code"],
                plan_id=plan.id,
                plan_snapshot={
                    "plan_id": str(plan.id),
                    "plan_code": plan.plan_code,
                    "name": plan.name,
                    "chitti_type": plan.chitti_type,
                    "total_value": float(total_value),
                    "currency": plan.currency,
                    "member_count": member_count,
                    "frequency": plan.frequency,
                    "duration": duration,
                    "contribution_rules": plan.contribution_rules,
                    "payout_rules": plan.payout_rules,
                },
                name=scenario["name"],
                branch="Hyderabad",
                start_date=start,
                end_date=end,
                member_count=member_count,
                total_value=total_value,
                current_period=0,
                status="RUNNING",
                notes="Seeded demo data for the analytics dashboard.",
                created_by=admin.id if admin else None,
            )
            session.add(chitti)
            await session.flush()

            # ---- period schedule ----
            schedules = {}
            for period in range(1, duration + 1):
                due = start + timedelta(days=days_per_period * (period - 1))
                expected = installment * member_count
                schedule = ChittiPeriodSchedule(
                    chitti_id=chitti.id,
                    period_number=period,
                    due_date=due,
                    expected_collection=expected,
                    actual_collection=ZERO,
                    pending_collection=expected,
                    expected_payout=installment * member_count,
                    actual_payout=ZERO,
                    status="UPCOMING",
                )
                session.add(schedule)
                schedules[period] = schedule

            # ---- members + contributions + ledger ----
            paid_by_period = {p: ZERO for p in range(1, duration + 1)}
            for index, customer in enumerate(customers[:member_count]):
                member = ChittiMember(
                    chitti_id=chitti.id,
                    customer_id=customer.id,
                    member_number=index + 1,
                    payout_order=index + 1,
                    status="ACTIVE",
                    total_expected_amount=installment * duration,
                    total_paid_amount=ZERO,
                    outstanding_amount=installment * duration,
                    lifted=False,
                )
                session.add(member)
                await session.flush()

                fractions = scenario["paid"].get(index, {})
                total_paid = ZERO
                for period in range(1, duration + 1):
                    fraction = Decimal(str(fractions.get(period, 0)))
                    paid = (installment * fraction).quantize(Decimal("0.01"))
                    due = schedules[period].due_date

                    if paid >= installment and installment > ZERO:
                        status = "PAID"
                    elif paid > ZERO:
                        status = "PARTIALLY_PAID"
                    elif due < today:
                        status = "OVERDUE"
                    else:
                        status = "UPCOMING"

                    session.add(
                        ChittiMemberContribution(
                            chitti_id=chitti.id,
                            member_id=member.id,
                            period_number=period,
                            expected_amount=installment,
                            paid_amount=paid,
                            remaining_amount=installment - paid,
                            status=status,
                        )
                    )
                    total_paid += paid
                    paid_by_period[period] += paid

                    if paid > ZERO:
                        method = METHOD_CYCLE[(index + period) % len(METHOD_CYCLE)]
                        session.add(
                            ChittiTransaction(
                                chitti_id=chitti.id,
                                transaction_type="CONTRIBUTION",
                                member_id=member.id,
                                amount=paid,
                                payment_method=method,
                                reference_number=f"{method[:3]}-{scenario['code'][-4:]}-{index + 1}-{period:02d}",
                                period_number=period,
                                notes=f"Demo contribution · period {period}",
                                created_by=admin.id if admin else None,
                                created_at=datetime.combine(
                                    due, time(5, 30), tzinfo=timezone.utc
                                ),
                            )
                        )

                member.total_paid_amount = total_paid
                member.outstanding_amount = (installment * duration) - total_paid

            # ---- roll up period schedules ----
            current_period = 0
            for period, schedule in schedules.items():
                actual = paid_by_period[period]
                schedule.actual_collection = actual
                schedule.pending_collection = max(schedule.expected_collection - actual, ZERO)
                if schedule.due_date <= today:
                    current_period = period
                if actual >= schedule.expected_collection and schedule.expected_collection > ZERO:
                    schedule.status = "COMPLETED"
                elif schedule.due_date < today:
                    schedule.status = "OVERDUE"
                elif schedule.due_date == today:
                    schedule.status = "ACTIVE"
                else:
                    schedule.status = "UPCOMING"

            chitti.current_period = current_period
            created.append(chitti.name)

        await session.commit()
        print("Seeded demo chittis:")
        for name in created:
            print(f"  • {name}")
        print("Done. Metrics are now computed from these real records.")


if __name__ == "__main__":
    asyncio.run(seed())
