from datetime import date, timedelta
from decimal import Decimal
import uuid

import pytest

from app.models.chitti import (
    Chitti,
    ChittiMember,
    ChittiMemberContribution,
    ChittiPeriodSchedule,
    ChittiPlan,
)
from app.models.customer import Customer
from app.models.finance import FinanceAccount, FinanceSchedule
from app.models.payment import PaymentTransaction
from app.utils.timezone import today_ist


@pytest.mark.asyncio
async def test_pending_collection_lists_only_due_unpaid_finance_and_chitti(client, test_user, db_session):
    """Due balances are listed once; future and settled periods stay out."""
    customer = Customer(
        customer_code=f"CUS-{uuid.uuid4().hex[:8]}",
        full_name="Pending Test Customer",
        mobile_number="9000000001",
        status="ACTIVE",
    )
    db_session.add(customer)
    await db_session.flush()

    account = FinanceAccount(
        account_number=f"FIN-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        principal_amount=Decimal("300"),
        interest_rate=Decimal("0"),
        interest_type="FLAT",
        fees=Decimal("0"),
        total_payable=Decimal("300"),
        installment_amount=Decimal("100"),
        frequency="DAILY",
        start_date=today_ist() - timedelta(days=2),
        first_due_date=today_ist() - timedelta(days=1),
        number_of_installments=3,
        status="ACTIVE",
    )
    db_session.add(account)
    await db_session.flush()

    due_date = today_ist() - timedelta(days=1)
    finance_partial = FinanceSchedule(
        finance_account_id=account.id,
        installment_number=1,
        due_date=due_date,
        expected_amount=Decimal("100"),
        paid_amount=Decimal("25"),
        remaining_amount=Decimal("75"),
        status="PARTIALLY_PAID",
    )
    finance_reversed = FinanceSchedule(
        finance_account_id=account.id,
        installment_number=2,
        due_date=due_date,
        expected_amount=Decimal("100"),
        paid_amount=Decimal("0"),
        remaining_amount=Decimal("100"),
        status="OVERDUE",
    )
    finance_future = FinanceSchedule(
        finance_account_id=account.id,
        installment_number=3,
        due_date=today_ist() + timedelta(days=1),
        expected_amount=Decimal("100"),
        paid_amount=Decimal("0"),
        remaining_amount=Decimal("100"),
        status="UPCOMING",
    )
    finance_settled = FinanceSchedule(
        finance_account_id=account.id,
        installment_number=4,
        due_date=due_date,
        expected_amount=Decimal("100"),
        paid_amount=Decimal("100"),
        remaining_amount=Decimal("0"),
        status="PAID",
    )
    db_session.add_all([finance_partial, finance_reversed, finance_future, finance_settled])
    await db_session.flush()

    original = PaymentTransaction(
        transaction_id=f"PAY-{uuid.uuid4().hex[:12]}",
        idempotency_key=f"pending-original-{uuid.uuid4().hex}",
        customer_id=customer.id,
        finance_account_id=account.id,
        finance_schedule_id=finance_reversed.id,
        amount=Decimal("100"),
        payment_method="CASH",
        payment_date=due_date,
        status="REVERSED",
    )
    db_session.add(original)
    await db_session.flush()
    db_session.add(PaymentTransaction(
        transaction_id=f"PAY-{uuid.uuid4().hex[:12]}",
        idempotency_key=f"pending-reversal-{uuid.uuid4().hex}",
        customer_id=customer.id,
        finance_account_id=account.id,
        finance_schedule_id=finance_reversed.id,
        amount=Decimal("-100"),
        payment_method="CASH",
        payment_date=due_date,
        is_reversal=True,
        reversed_by=original.id,
        status="COMPLETED",
    ))

    plan = ChittiPlan(
        plan_code=f"PLN-{uuid.uuid4().hex[:8]}",
        name="Pending Test Chitti Plan",
        chitti_type="FIXED",
        total_value=Decimal("300"),
        member_count=1,
        frequency="DAILY",
        duration=3,
        contribution_rules={"type": "FIXED", "installment_amount": "100"},
        payout_rules={"type": "SCHEDULED"},
        created_by=test_user["user"].id,
    )
    db_session.add(plan)
    await db_session.flush()

    chitti = Chitti(
        chitti_code=f"CHIT-{uuid.uuid4().hex[:8]}",
        plan_id=plan.id,
        plan_snapshot={
            "chitti_type": "FIXED",
            "total_value": "300",
            "member_count": 1,
            "frequency": "DAILY",
            "duration": 3,
            "contribution_rules": {"type": "FIXED", "installment_amount": "100"},
            "payout_rules": {"type": "SCHEDULED"},
        },
        name="Pending Test Chitti",
        start_date=today_ist() - timedelta(days=2),
        end_date=today_ist() + timedelta(days=1),
        member_count=1,
        total_value=Decimal("300"),
        current_period=1,
        status="RUNNING",
        created_by=test_user["user"].id,
    )
    db_session.add(chitti)
    await db_session.flush()

    member = ChittiMember(
        chitti_id=chitti.id,
        customer_id=customer.id,
        member_number=1,
        status="ACTIVE",
    )
    db_session.add(member)
    await db_session.flush()

    chitti_periods = [
        ChittiPeriodSchedule(
            chitti_id=chitti.id,
            period_number=period,
            due_date=period_due,
            expected_collection=Decimal("100"),
            actual_collection=Decimal("0"),
            pending_collection=Decimal("100"),
            expected_payout=Decimal("0"),
            actual_payout=Decimal("0"),
            status="OVERDUE" if period_due < today_ist() else "UPCOMING",
        )
        for period, period_due in ((1, due_date), (2, today_ist() + timedelta(days=1)), (3, due_date))
    ]
    db_session.add_all(chitti_periods)
    db_session.add_all([
        ChittiMemberContribution(
            chitti_id=chitti.id,
            member_id=member.id,
            period_number=1,
            expected_amount=Decimal("100"),
            paid_amount=Decimal("30"),
            remaining_amount=Decimal("70"),
            status="PARTIALLY_PAID",
        ),
        ChittiMemberContribution(
            chitti_id=chitti.id,
            member_id=member.id,
            period_number=2,
            expected_amount=Decimal("100"),
            paid_amount=Decimal("0"),
            remaining_amount=Decimal("100"),
            status="UPCOMING",
        ),
        ChittiMemberContribution(
            chitti_id=chitti.id,
            member_id=member.id,
            period_number=3,
            expected_amount=Decimal("100"),
            paid_amount=Decimal("100"),
            remaining_amount=Decimal("0"),
            status="PAID",
        ),
    ])
    await db_session.flush()

    response = await client.get(
        "/api/v1/payments/pending",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200, response.text
    records = response.json()["data"]

    assert len(records) == 3
    assert len({record["id"] for record in records}) == 3
    finance_rows = [row for row in records if row["source"] == "FINANCE"]
    chitti_rows = [row for row in records if row["source"] == "CHITTI"]
    assert {(row["period_number"], row["outstanding_amount"], row["status"]) for row in finance_rows} == {
        (1, 75.0, "PARTIALLY_PAID"),
        (2, 100.0, "OVERDUE"),
    }
    assert len(chitti_rows) == 1
    assert chitti_rows[0]["period_number"] == 1
    assert chitti_rows[0]["expected_amount"] == 100.0
    assert chitti_rows[0]["outstanding_amount"] == 70.0
    assert chitti_rows[0]["status"] == "PARTIALLY_PAID"
    assert all(row["customer_code"] == customer.customer_code for row in records)
    assert all(row["mobile_number"] == customer.mobile_number for row in records)
    assert all(row["due_date"] <= date.today().isoformat() for row in records)
