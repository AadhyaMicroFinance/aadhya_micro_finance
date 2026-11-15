"""Focused customer profile payment-history regression coverage."""

from datetime import date
from decimal import Decimal
import uuid

import pytest


async def _add_chitti_payment_data(session, customer, *, reverse_second=False):
    from app.models.chitti import Chitti, ChittiMember, ChittiPlan, ChittiTransaction

    plan = ChittiPlan(
        plan_code=f"PLN-{uuid.uuid4().hex[:8]}", name="History test plan",
        chitti_type="FIXED", total_value=Decimal("300"), member_count=1,
        frequency="DAILY", duration=3,
        contribution_rules={"type": "FIXED", "amount": 100},
        payout_rules={"type": "SCHEDULED"},
    )
    session.add(plan)
    await session.flush()
    chitti = Chitti(
        chitti_code=f"CHT-{uuid.uuid4().hex[:8]}", plan_id=plan.id,
        plan_snapshot={}, name="History Test Chitti", start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3), member_count=1, total_value=Decimal("300"),
    )
    session.add(chitti)
    await session.flush()
    member = ChittiMember(chitti_id=chitti.id, customer_id=customer.id, member_number=1)
    session.add(member)
    await session.flush()
    transactions = []
    for period in range(1, 4):
        transaction = ChittiTransaction(
            chitti_id=chitti.id, member_id=member.id, transaction_type="CONTRIBUTION",
            amount=Decimal("100"), payment_method="CASH", period_number=period,
            payment_date=date(2026, 1, period), idempotency_key=f"test-chitti-{period}-{uuid.uuid4()}",
        )
        session.add(transaction)
        transactions.append(transaction)
    await session.flush()
    if reverse_second:
        session.add(ChittiTransaction(
            chitti_id=chitti.id, member_id=member.id, transaction_type="REVERSAL",
            amount=Decimal("100"), payment_method="CASH", period_number=2,
            payment_date=date(2026, 1, 4),
            idempotency_key=f"test-reversal-{uuid.uuid4()}",
            notes=f"Reversal of {transactions[1].id}: test reversal",
        ))
        await session.flush()
    return transactions


async def _add_finance_payment_data(session, customer, *, reversed_payment=False):
    from app.models.finance import FinanceAccount, FinanceSchedule
    from app.models.payment import PaymentTransaction

    account = FinanceAccount(
        account_number=f"FIN-{uuid.uuid4().hex[:8]}", customer_id=customer.id,
        principal_amount=Decimal("100"), interest_rate=Decimal("0"), interest_type="FLAT",
        fees=Decimal("0"), total_payable=Decimal("100"), installment_amount=Decimal("100"),
        frequency="DAILY", start_date=date(2026, 1, 1), first_due_date=date(2026, 1, 1),
        number_of_installments=1,
    )
    session.add(account)
    await session.flush()
    schedule = FinanceSchedule(
        finance_account_id=account.id, installment_number=1, due_date=date(2026, 1, 1),
        expected_amount=Decimal("100"), paid_amount=Decimal("100"), remaining_amount=Decimal("0"),
        status="PAID",
    )
    session.add(schedule)
    await session.flush()
    original = PaymentTransaction(
        transaction_id=f"PAY-{uuid.uuid4().hex[:8]}", idempotency_key=f"finance-{uuid.uuid4()}",
        customer_id=customer.id, finance_account_id=account.id, finance_schedule_id=schedule.id,
        amount=Decimal("100"), payment_method="UPI", payment_date=date(2026, 1, 1),
        status="REVERSED" if reversed_payment else "COMPLETED",
    )
    session.add(original)
    await session.flush()
    if reversed_payment:
        reversal = PaymentTransaction(
            transaction_id=f"PAY-{uuid.uuid4().hex[:8]}", idempotency_key=f"reversal-{uuid.uuid4()}",
            customer_id=customer.id, finance_account_id=account.id, finance_schedule_id=schedule.id,
            amount=Decimal("100"), payment_method="UPI", payment_date=date(2026, 1, 2),
            status="REVERSED", is_reversal=True, reversed_by=original.id,
        )
        session.add(reversal)
        await session.flush()
    return account, original


@pytest.mark.asyncio
async def test_customer_payment_history_reads_chitti_only_once(client, db_session, test_user, test_customer):
    transactions = await _add_chitti_payment_data(db_session, test_customer)
    response = await client.get(
        f"/api/v1/customers/{test_customer.id}/ledger",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    history = data["payment_history"]
    assert len(history) == 3
    assert len({row["id"] for row in history}) == 3
    assert {row["source"] for row in history} == {"CHITTI"}
    assert {row["account_name"] for row in history} == {"History Test Chitti"}
    assert {row["period_number"] for row in history} == {1, 2, 3}
    assert sum(row["amount"] for row in history) == 300
    assert data["payment_summary"] == {
        "transaction_count": 3,
        "successful_transaction_count": 3,
        "successful_paid_total": 300,
    }
    assert {f"CHT-{transaction.id}" for transaction in transactions} == {
        row["transaction_id"] for row in history
    }


@pytest.mark.asyncio
async def test_customer_payment_history_keeps_finance_only_history_working(
    client, db_session, test_user, test_customer
):
    account, payment = await _add_finance_payment_data(db_session, test_customer)
    response = await client.get(
        f"/api/v1/customers/{test_customer.id}/ledger",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["payment_history"]) == 1
    row = data["payment_history"][0]
    assert row["source"] == "FINANCE"
    assert row["transaction_id"] == payment.transaction_id
    assert row["account_name"] == account.account_number
    assert row["period_number"] == 1
    assert row["status"] == "COMPLETED"
    assert data["payment_summary"]["successful_paid_total"] == 100


@pytest.mark.asyncio
async def test_customer_payment_history_keeps_finance_and_chitti_separate_and_marks_reversals(
    client, db_session, test_user, test_customer
):
    await _add_chitti_payment_data(db_session, test_customer, reverse_second=True)
    account, _ = await _add_finance_payment_data(db_session, test_customer, reversed_payment=True)
    response = await client.get(
        f"/api/v1/customers/{test_customer.id}/ledger",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    history = data["payment_history"]
    assert len(history) == 6  # 3 Chitti contributions + reversal + 2 Finance entries
    assert len({(row["source"], row["id"]) for row in history}) == len(history)
    assert {row["source"] for row in history} == {"FINANCE", "CHITTI"}
    finance = [row for row in history if row["source"] == "FINANCE"]
    assert {row["account_name"] for row in finance} == {account.account_number}
    assert sum(row["amount"] for row in finance if row["status"] == "COMPLETED") == 0
    assert any(row["is_reversal"] and row["reversal_of_transaction_id"] for row in finance)
    chitti = [row for row in history if row["source"] == "CHITTI"]
    assert sum(row["amount"] for row in chitti if row["status"] == "COMPLETED") == 200
    assert any(row["status"] == "REVERSED" and row["reversed_by_transaction_id"] for row in chitti)
    assert data["payment_summary"]["transaction_count"] == 6
    assert data["payment_summary"]["successful_paid_total"] == 200
    assert data["customer"]["full_name"] == test_customer.full_name
