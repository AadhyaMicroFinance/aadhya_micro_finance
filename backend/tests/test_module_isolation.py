"""
Finance / Money Budget Schemes (Chitti) module-isolation regressions.

These tests protect the mandated architecture:

  * one shared Customer Master with no module-specific financial fields;
  * two independent financial ledgers (``payment_transactions`` for Finance,
    ``chitti_transactions`` for Chitti);
  * no shared calculation or balance-update logic;
  * no direct cross-module financial mutation.

All data is created in the disposable scratch database via the standard
fixtures; no development/production records are touched.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select

from app.models.chitti import ChittiMember, ChittiMemberContribution, ChittiTransaction
from app.models.customer import Customer
from app.models.finance import FinanceAccount, FinanceSchedule
from app.models.payment import PaymentTransaction
from tests.finance_helpers import create_finance_account

PLAN = {
    "name": "Isolation Test Chitti Plan",
    "chitti_type": "FIXED",
    "total_value": "100.00",
    "member_count": 1,
    "frequency": "DAILY",
    "duration": 1,
    "contribution_rules": {
        "type": "FIXED",
        "installment_amount": "100.00",
        "partial_payments_allowed": True,
    },
    "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
}


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _create_customer(client, headers, name, mobile):
    response = await client.post(
        "/api/v1/customers/",
        json={"full_name": name, "mobile_number": mobile, "address": "Hyderabad"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_payment_ledger_schema_is_finance_only(test_engine):
    """payment_transactions must not carry Chitti columns or foreign keys."""

    def _inspect(sync_conn):
        inspector = inspect(sync_conn)
        return {
            "tables": set(inspector.get_table_names()),
            "columns": {column["name"] for column in inspector.get_columns("payment_transactions")},
            "fks": inspector.get_foreign_keys("payment_transactions"),
        }

    async with test_engine.connect() as connection:
        schema = await connection.run_sync(_inspect)

    assert "chitti_account_id" not in schema["columns"]
    assert "chitti_schedule_id" not in schema["columns"]
    assert all(
        foreign_key["referred_table"] not in {"chittis", "chitti_period_schedule"}
        for foreign_key in schema["fks"]
    )
    # Chitti owns its own financial ledger; it is never stored in the Finance table.
    assert "chitti_transactions" in schema["tables"]
    assert "finance_accounts" in schema["tables"]
    assert "finance_schedules" in schema["tables"]


@pytest.mark.asyncio
async def test_customer_master_owns_no_module_financial_fields(test_engine):
    """The shared Customer Master must stay free of module financial state."""

    def _customer_columns(sync_conn):
        return {column["name"] for column in inspect(sync_conn).get_columns("customers")}

    async with test_engine.connect() as connection:
        columns = await connection.run_sync(_customer_columns)

    forbidden = {
        "balance",
        "outstanding_amount",
        "total_paid",
        "total_payable",
        "finance_account_id",
        "chitti_id",
        "ledger_id",
        "schedule_id",
        "transaction_id",
        "agreement_id",
    }
    assert not (columns & forbidden), columns & forbidden


@pytest.mark.asyncio
async def test_finance_repayment_does_not_mutate_chitti_ledger(client, test_user, db_session):
    """Recording a Finance repayment never writes to Chitti-owned records."""
    headers = _auth(test_user)
    customer = await _create_customer(client, headers, "Isolation Finance Payer", "9100000001")
    account, _ = await create_finance_account(
        client,
        headers,
        customer["id"],
        principal_amount="100.00",
    )

    schedule_rows = await db_session.execute(
        select(FinanceSchedule).where(FinanceSchedule.finance_account_id == account["id"])
    )
    installments = schedule_rows.scalars().all()
    assert installments

    chitti_before = await db_session.scalar(select(func.count()).select_from(ChittiTransaction))
    contributions_before = await db_session.scalar(
        select(func.count()).select_from(ChittiMemberContribution)
    )
    finance_before = await db_session.scalar(select(func.count()).select_from(PaymentTransaction))

    payment = await client.post(
        "/api/v1/payments/",
        json={
            "customer_id": customer["id"],
            "finance_account_id": account["id"],
            "finance_schedule_id": str(installments[0].id),
            "amount": "100.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "isolation-finance-repayment",
        },
        headers=headers,
    )
    assert payment.status_code == 200, payment.text

    assert await db_session.scalar(select(func.count()).select_from(ChittiTransaction)) == chitti_before
    assert await db_session.scalar(
        select(func.count()).select_from(ChittiMemberContribution)
    ) == contributions_before
    assert await db_session.scalar(select(func.count()).select_from(PaymentTransaction)) == finance_before + 1

    await db_session.refresh(installments[0])
    assert installments[0].paid_amount == Decimal("100.00")
    assert installments[0].remaining_amount == Decimal("0")


@pytest.mark.asyncio
async def test_chitti_contribution_does_not_mutate_finance_ledger(client, test_user, db_session):
    """Recording a Chitti contribution never writes to Finance-owned records."""
    headers = _auth(test_user)
    customer = await _create_customer(client, headers, "Isolation Chitti Contributor", "9100000002")

    plan_response = await client.post("/api/v1/chitti/plans", json=PLAN, headers=headers)
    assert plan_response.status_code == 200, plan_response.text
    chitti_response = await client.post(
        "/api/v1/chitti/",
        json={
            "plan_id": plan_response.json()["data"]["id"],
            "name": "Isolation Chitti",
            "member_count": 1,
            "start_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert chitti_response.status_code == 200, chitti_response.text
    chitti_id = chitti_response.json()["data"]["id"]

    member_response = await client.post(
        f"/api/v1/chitti/{chitti_id}/members",
        json={"customer_id": customer["id"]},
        headers=headers,
    )
    assert member_response.status_code == 200, member_response.text
    member_id = member_response.json()["data"]["id"]
    for action in ("generate", "print", "confirm"):
        agreement = await client.post(
            f"/api/v1/chitti/{chitti_id}/members/{member_id}/agreement/{action}",
            headers=headers,
        )
        assert agreement.status_code == 200, agreement.text
    start = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert start.status_code == 200, start.text

    finance_before = await db_session.scalar(select(func.count()).select_from(PaymentTransaction))
    accounts_before = await db_session.scalar(select(func.count()).select_from(FinanceAccount))
    schedules_before = await db_session.scalar(select(func.count()).select_from(FinanceSchedule))
    chitti_before = await db_session.scalar(select(func.count()).select_from(ChittiTransaction))

    contribution = await client.post(
        f"/api/v1/chitti/{chitti_id}/contributions",
        json={
            "member_id": member_id,
            "period_number": 1,
            "amount": "100.00",
            "payment_method": "UPI",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "isolation-chitti-contribution",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text

    assert await db_session.scalar(select(func.count()).select_from(PaymentTransaction)) == finance_before
    assert await db_session.scalar(select(func.count()).select_from(FinanceAccount)) == accounts_before
    assert await db_session.scalar(select(func.count()).select_from(FinanceSchedule)) == schedules_before
    assert await db_session.scalar(select(func.count()).select_from(ChittiTransaction)) >= chitti_before + 1

    member = await db_session.get(ChittiMember, member_id)
    assert member is not None
    assert member.outstanding_amount == Decimal("0")


@pytest.mark.asyncio
async def test_finance_payment_contract_rejects_chitti_fields(client, test_user):
    """Chitti fields are not part of the Finance payment contract at all."""
    headers = _auth(test_user)
    blocked = await client.post(
        "/api/v1/payments/",
        json={
            "customer_id": "00000000-0000-0000-0000-000000000001",
            "finance_account_id": "00000000-0000-0000-0000-000000000002",
            "finance_schedule_id": "00000000-0000-0000-0000-000000000003",
            "chitti_account_id": "00000000-0000-0000-0000-000000000004",
            "amount": "10.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "isolation-reject-chitti-field",
        },
        headers=headers,
    )
    assert blocked.status_code == 422, blocked.text
    assert "chitti_account_id" in blocked.text
