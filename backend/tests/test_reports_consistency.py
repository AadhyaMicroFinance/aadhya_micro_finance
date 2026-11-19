"""
Dashboard / report consistency tests (BUG-005, BUG-006, BUG-007).

These prove the dashboard reads the real money ledgers:
  * finance money  -> `payment_transactions`
  * chitti money   -> `chitti_transactions`
and that the two streams are reported separately while still adding up to the
headline total. They also prove a chitti contribution can be collected without
any finance account, and that a retried save cannot double-count money.
"""

import math
import csv
import asyncio
from io import BytesIO, StringIO
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.models.audit import AuditLog
from app.models.payment import PaymentTransaction
from app.models.chitti import (
    ChittiMember,
    ChittiMemberContribution,
    ChittiPeriodSchedule,
    ChittiPayout,
    ChittiTransaction,
    ChittiLiftEvent,
)
from app.repositories.chitti_repo import ChittiTransactionRepository
from app.repositories.audit_repo import AuditLogRepository
from app.services.chitti_service import ChittiService

PLAN = {
    "name": "Report Consistency Plan",
    "chitti_type": "FIXED",
    "total_value": "10000.00",
    "member_count": 4,
    "frequency": "WEEKLY",
    "duration": 10,
    "contribution_rules": {
        "type": "FIXED",
        "installment_amount": "1000.00",
        "partial_payments_allowed": True,
    },
    "payout_rules": {"type": "SCHEDULED"},
}


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _customer(client, headers, index):
    resp = await client.post(
        "/api/v1/customers/",
        json={
            "full_name": f"Report Member {index}",
            "mobile_number": f"93300000{index:02d}",
            "address": "Hyderabad, Telangana",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _activate_member(client, headers, chitti_id, member_id):
    for action in ("generate", "print", "confirm"):
        resp = await client.post(
            f"/api/v1/chitti/{chitti_id}/members/{member_id}/agreement/{action}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


async def _running_chitti(client, headers, members=2):
    """Create a Chitti and start it explicitly after confirming agreements."""
    plan = (
        await client.post("/api/v1/chitti/plans", json=PLAN, headers=headers)
    ).json()["data"]
    chitti = (
        await client.post(
            "/api/v1/chitti/",
            json={
                "plan_id": plan["id"],
                "name": "Report Chitti",
                "start_date": date.today().isoformat(),
                "member_count": 4,
            },
            headers=headers,
        )
    ).json()["data"]

    enrolled = []
    for index in range(1, members + 1):
        customer = await _customer(client, headers, index)
        member = (
            await client.post(
                f"/api/v1/chitti/{chitti['id']}/members",
                json={"customer_id": customer["id"], "payout_order": index},
                headers=headers,
            )
        ).json()["data"]
        enrolled.append(member)

    confirmation = None
    for member in enrolled:
        confirmation = None
        for action in ("generate", "print", "confirm"):
            resp = await client.post(
                f"/api/v1/chitti/{chitti['id']}/members/{member['id']}/agreement/{action}",
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            if action == "confirm":
                confirmation = resp.json()["data"]
    assert confirmation["chitti_auto_started"] is False
    assert confirmation["chitti_status"] == "DRAFT"
    started = await client.post(f"/api/v1/chitti/{chitti['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["data"]["status"] == "RUNNING"
    return chitti, enrolled


async def _running_lift_chitti(client, headers, member_count=2):
    plan = (
        await client.post("/api/v1/chitti/plans", json={
            "name": "P0.3 Concurrent Lift Plan",
            "chitti_type": "LIFT_BASED",
            "total_value": "120000.00",
            "member_count": member_count,
            "frequency": "DAILY",
            "duration": 4,
            "contribution_rules": {
                "type": "LIFT_BASED",
                "regular_amount": "5000.00",
            },
            "payout_rules": {
                "type": "SCHEDULED",
                "payout_order": "MEMBER_NUMBER",
            },
        }, headers=headers)
    ).json()["data"]
    chitti = (
        await client.post("/api/v1/chitti/", json={
            "plan_id": plan["id"],
            "name": "P0.3 Concurrent Lift Chitti",
            "member_count": member_count,
            "start_date": date.today().isoformat(),
        }, headers=headers)
    ).json()["data"]

    enrolled = []
    for index in range(1, member_count + 1):
        customer = await _customer(client, headers, index + 20)
        member = (
            await client.post(
                f"/api/v1/chitti/{chitti['id']}/members",
                json={"customer_id": customer["id"], "payout_order": index},
                headers=headers,
            )
        ).json()["data"]
        enrolled.append(member)
        await _activate_member(client, headers, chitti["id"], member["id"])

    started = await client.post(f"/api/v1/chitti/{chitti['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["data"]["status"] == "RUNNING"
    return chitti, enrolled


@pytest.mark.asyncio
async def test_reversal_restores_schedule_and_report(client, test_user, db_session):
    """A reversed payment must free the installment again and net out."""
    headers = _auth(test_user)
    today = date.today().isoformat()
    customer = await _customer(client, headers, 7)

    account = (
        await client.post(
            "/api/v1/finance/",
            json={
                "customer_id": customer["id"],
                "principal_amount": "3000.00",
                "interest_rate": "0",
                "interest_type": "FLAT",
                "fees": "0",
                "frequency": "WEEKLY",
                "start_date": today,
                "first_due_date": today,
                "number_of_installments": 3,
            },
            headers=headers,
        )
    ).json()["data"]

    schedule = (
        await client.get(f"/api/v1/finance/{account['id']}/schedule", headers=headers)
    ).json()["data"]
    installment = next(s for s in schedule if s["due_date"] == today)

    # A chitti id on the finance endpoint would double-count money.
    blocked = await client.post(
        "/api/v1/payments/",
        json={
            "customer_id": customer["id"],
            "chitti_account_id": account["id"],
            "amount": "100.00",
            "payment_method": "CASH",
            "payment_date": today,
            "idempotency_key": "chitti-money-on-finance-endpoint",
        },
        headers=headers,
    )
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["error"]["code"] == "USE_CHITTI_CONTRIBUTION_ENDPOINT"

    payment_body = {
                "customer_id": customer["id"],
                "finance_account_id": account["id"],
                "finance_schedule_id": installment["id"],
                "amount": "1000.00",
                "payment_method": "CASH",
                "payment_date": today,
                "idempotency_key": "reversal-test-1",
    }
    payment_response = await client.post("/api/v1/payments/", json=payment_body, headers=headers)
    assert payment_response.status_code == 200, payment_response.text
    payment = payment_response.json()["data"]

    duplicate = await client.post("/api/v1/payments/", json=payment_body, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_PAYMENT"

    paid_row = next(
        s
        for s in (
            await client.get(f"/api/v1/finance/{account['id']}/schedule", headers=headers)
        ).json()["data"]
        if s["id"] == installment["id"]
    )
    assert paid_row["status"] == "PAID"
    assert paid_row["paid_amount"] == 1000.0
    assert paid_row["remaining_amount"] == 0.0

    reversal = await client.post(
        f"/api/v1/payments/{payment['id']}/reverse",
        json={"reversal_reason": "cash returned"},
        headers=headers,
    )
    assert reversal.status_code == 200, reversal.text

    restored = next(
        s
        for s in (
            await client.get(f"/api/v1/finance/{account['id']}/schedule", headers=headers)
        ).json()["data"]
        if s["id"] == installment["id"]
    )
    assert restored["paid_amount"] == 0.0, "the installment must be unpaid again"
    assert restored["remaining_amount"] == 1000.0
    assert restored["status"] in ("UPCOMING", "OVERDUE")

    report = (
        await client.get(f"/api/v1/reports/daily?date={today}", headers=headers)
    ).json()["data"]
    assert report["finance_collected"] == 0.0
    assert report["finance_reversals"] == 1000.0
    assert report["net_collections"] == -1000.0
    assert report["finance_pending"] == 1000.0

    ledger = list((await db_session.execute(select(PaymentTransaction))).scalars().all())
    assert len(ledger) == 2, "reversal must append a ledger row and retain the original"
    assert sum(1 for row in ledger if row.is_reversal) == 1
    audit = list((await db_session.execute(
        select(AuditLog).where(AuditLog.action == "FINANCE_PAYMENT_REVERSED")
    )).scalars().all())
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_chitti_partial_reversal_restores_ledger_and_audit(client, test_user, db_session):
    headers = _auth(test_user)
    today = date.today().isoformat()
    chitti, members = await _running_chitti(client, headers, members=1)
    eligible = (await client.get(
        f"/api/v1/payments/customer/{members[0]['customer_id']}/eligible-accounts",
        headers=headers,
    )).json()["data"]
    assert eligible["finance_accounts"] == []
    assert [item["chitti_id"] for item in eligible["chitti_memberships"]] == [chitti["id"]]
    contribution = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"], "period_number": 1,
            "amount": "400.00", "payment_method": "CASH",
            "payment_date": today, "idempotency_key": "chitti-reversal-origin",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
    original_id = contribution.json()["data"]["transaction_id"]

    reversal = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{original_id}/reverse",
        json={"reversal_reason": "regression reversal"}, headers=headers,
    )
    assert reversal.status_code == 200, reversal.text
    assert reversal.json()["data"]["duplicate"] is False
    repeated = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{original_id}/reverse",
        json={"reversal_reason": "retry"}, headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["duplicate"] is True

    rows = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/members/{members[0]['id']}/contributions",
        headers=headers,
    )).json()["data"]
    first_period = next(row for row in rows if row["period_number"] == 1)
    assert float(first_period["paid_amount"]) == 0.0
    assert float(first_period["remaining_amount"]) == 1000.0
    assert first_period["status"] in ("UPCOMING", "OVERDUE")

    audit = list((await db_session.execute(
        select(AuditLog).where(AuditLog.action == "CHITTI_CONTRIBUTION_REVERSED")
    )).scalars().all())
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_concurrent_chitti_reversals_create_one_reversal(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    today = date.today().isoformat()
    contribution = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "400.00",
            "payment_method": "CASH",
            "payment_date": today,
            "idempotency_key": "concurrent-reversal-origin",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
    transaction_id = contribution.json()["data"]["transaction_id"]
    await db_session.commit()

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def reverse(label: str):
        async with sessions() as session:
            try:
                result = await ChittiService(session).reverse_contribution(
                    UUID(chitti["id"]),
                    UUID(transaction_id),
                    reason=f"concurrent {label}",
                    reversed_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(reverse("a"), reverse("b"))
    assert sum(isinstance(value, dict) for value in results) == 2
    assert sum(value.get("duplicate") is False for value in results if isinstance(value, dict)) == 1
    assert sum(value.get("duplicate") is True for value in results if isinstance(value, dict)) == 1

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
                ChittiTransaction.transaction_type == "REVERSAL",
            )
        )).scalars().all())
        assert len(ledger) == 1

        contribution_rows = list((await fresh.execute(
            select(ChittiMemberContribution).where(
                ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                ChittiMemberContribution.period_number == 1,
            )
        )).scalars().all())
        assert len(contribution_rows) == 1
        assert contribution_rows[0].paid_amount == Decimal("0")
        assert contribution_rows[0].remaining_amount == Decimal("1000")

        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_CONTRIBUTION_REVERSED")
        )).scalars().all())
        assert len(audit) == 1


@pytest.mark.asyncio
async def test_reversal_concurrent_with_collection_preserves_totals(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    today = date.today().isoformat()
    contribution = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "400.00",
            "payment_method": "CASH",
            "payment_date": today,
            "idempotency_key": "reversal-vs-collection-origin",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
    transaction_id = contribution.json()["data"]["transaction_id"]
    await db_session.commit()

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def reverse():
        async with sessions() as session:
            try:
                result = await ChittiService(session).reverse_contribution(
                    UUID(chitti["id"]),
                    UUID(transaction_id),
                    reason="reversal race",
                    reversed_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    async def collect():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_contribution(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    amount=Decimal("600.00"),
                    payment_method="UPI",
                    payment_date=date.today(),
                    idempotency_key="reversal-vs-collection-600",
                    created_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(reverse(), collect())
    assert all(isinstance(value, dict) for value in results)
    reverse_result, collection_result = results
    assert reverse_result["duplicate"] is False
    assert collection_result["duplicate"] is False

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        member_row = (
            await fresh.execute(
                select(ChittiMemberContribution).where(
                    ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                    ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                )
            )
        ).scalars().all()
        assert sum((row.paid_amount for row in member_row), Decimal("0")) == Decimal("600")
        assert sum((row.remaining_amount for row in member_row), Decimal("0")) == Decimal("9400")

        schedule = (
            await fresh.execute(
                select(ChittiPeriodSchedule).where(
                    ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
                    ChittiPeriodSchedule.period_number == 1,
                )
            )
        ).scalar_one()
        assert schedule.actual_collection == Decimal("600")
        assert schedule.pending_collection == Decimal("400")

        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
                ChittiTransaction.period_number == 1,
            )
        )).scalars().all())
        assert len(ledger) == 3
        assert sum(row.transaction_type == "CONTRIBUTION" for row in ledger) == 2
        assert sum(row.transaction_type == "REVERSAL" for row in ledger) == 1


@pytest.mark.asyncio
async def test_reversal_rejects_insufficient_balance_and_invalid_type(
    client, test_user, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)

    genuine = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "400.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "genuine-insufficient-reversal-origin",
        },
        headers=headers,
    )
    assert genuine.status_code == 200, genuine.text
    genuine_transaction_id = genuine.json()["data"]["transaction_id"]
    contribution_row = (
        await db_session.execute(
            select(ChittiMemberContribution).where(
                ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                ChittiMemberContribution.period_number == 1,
            )
        )
    ).scalar_one()
    contribution_row.paid_amount = Decimal("100")
    contribution_row.remaining_amount = Decimal("900")
    await db_session.flush()

    insufficient_response = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{genuine_transaction_id}/reverse",
        json={"reversal_reason": "balance does not support reversal"},
        headers=headers,
    )
    assert insufficient_response.status_code == 400
    assert insufficient_response.json()["error"]["code"] == "BAD_REQUEST"

    invalid = ChittiTransaction(
        chitti_id=UUID(chitti["id"]),
        transaction_type="PAYOUT",
        member_id=UUID(members[0]["id"]),
        amount=Decimal("100"),
        payment_method="CASH",
        period_number=1,
        idempotency_key="invalid-reversal-type",
    )
    db_session.add(invalid)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{invalid.id}/reverse",
        json={"reversal_reason": "invalid transaction type"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_repeated_reversal_uses_separate_sessions_without_second_mutation(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    contribution = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "400.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "separate-session-reversal-origin",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
    transaction_id = contribution.json()["data"]["transaction_id"]
    await db_session.commit()

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with sessions() as first:
        first_result = await ChittiService(first).reverse_contribution(
            UUID(chitti["id"]),
            UUID(transaction_id),
            reason="first reversal",
            reversed_by=test_user["user"].id,
        )
        await first.commit()

    async with sessions() as repeated:
        repeated_result = await ChittiService(repeated).reverse_contribution(
            UUID(chitti["id"]),
            UUID(transaction_id),
            reason="repeated reversal",
            reversed_by=test_user["user"].id,
        )
        await repeated.commit()

    assert first_result["duplicate"] is False
    assert repeated_result["duplicate"] is True

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
            )
        )).scalars().all())
        assert sum(row.transaction_type == "CONTRIBUTION" for row in ledger) == 1
        assert sum(row.transaction_type == "REVERSAL" for row in ledger) == 1

        contribution_row = (
            await fresh.execute(
                select(ChittiMemberContribution).where(
                    ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                    ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                    ChittiMemberContribution.period_number == 1,
                )
            )
        ).scalar_one()
        assert contribution_row.paid_amount == Decimal("0")
        assert contribution_row.remaining_amount == Decimal("1000")

        member_row = (
            await fresh.execute(
                select(ChittiMember).where(
                    ChittiMember.chitti_id == UUID(chitti["id"]),
                    ChittiMember.id == UUID(members[0]["id"]),
                )
            )
        ).scalar_one()
        assert member_row.total_paid_amount == Decimal("0")
        assert member_row.outstanding_amount == Decimal("10000")

        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_CONTRIBUTION_REVERSED")
        )).scalars().all())
        assert len(audit) == 1


@pytest.mark.asyncio
async def test_reversal_rolls_back_after_controlled_post_lock_failure(
    client, test_user, test_engine, db_session, monkeypatch
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    contribution = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "400.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "rollback-reversal-origin",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
    transaction_id = contribution.json()["data"]["transaction_id"]
    await db_session.commit()

    async def fail_reversal_ledger_create(self, **kwargs):
        raise RuntimeError("controlled failure after reversal locks and balance validation")

    monkeypatch.setattr(
        ChittiTransactionRepository,
        "create",
        fail_reversal_ledger_create,
    )

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        with pytest.raises(RuntimeError, match="controlled failure"):
            await ChittiService(session).reverse_contribution(
                UUID(chitti["id"]),
                UUID(transaction_id),
                reason="test rollback",
                reversed_by=test_user["user"].id,
            )
        await session.rollback()

    monkeypatch.undo()

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        contribution_row = (
            await fresh.execute(
                select(ChittiMemberContribution).where(
                    ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                    ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                    ChittiMemberContribution.period_number == 1,
                )
            )
        ).scalar_one()
        assert contribution_row.paid_amount == Decimal("400")
        assert contribution_row.remaining_amount == Decimal("600")
        assert contribution_row.status == "PARTIALLY_PAID"

        schedule = (
            await fresh.execute(
                select(ChittiPeriodSchedule).where(
                    ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
                    ChittiPeriodSchedule.period_number == 1,
                )
            )
        ).scalar_one()
        assert schedule.actual_collection == Decimal("400")
        assert schedule.pending_collection == Decimal("600")

        member_row = (
            await fresh.execute(
                select(ChittiMember).where(
                    ChittiMember.chitti_id == UUID(chitti["id"]),
                    ChittiMember.id == UUID(members[0]["id"]),
                )
            )
        ).scalar_one()
        assert member_row.total_paid_amount == Decimal("400")
        assert member_row.outstanding_amount == Decimal("9600")

        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
            )
        )).scalars().all())
        assert sum(row.transaction_type == "CONTRIBUTION" for row in ledger) == 1
        assert sum(row.transaction_type == "REVERSAL" for row in ledger) == 0

        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_CONTRIBUTION_REVERSED")
        )).scalars().all())
        assert len(audit) == 0


@pytest.mark.asyncio
async def test_normal_and_duplicate_payout_posting(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    payout_body = {
        "member_id": members[0]["id"],
        "period_number": 1,
        "gross_payout": "1000.00",
        "discount_amount": "100.00",
        "fee_amount": "50.00",
        "net_payout": "850.00",
        "payout_method": "CASH",
        "idempotency_key": "normal-payout-repeat",
    }

    first = await client.post(
        f"/api/v1/chitti/{chitti['id']}/payouts",
        json=payout_body,
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["duplicate"] is False
    await db_session.commit()

    repeated = await client.post(
        f"/api/v1/chitti/{chitti['id']}/payouts",
        json=payout_body,
        headers=headers,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["data"]["duplicate"] is True
    await db_session.commit()

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        payouts = list((await fresh.execute(
            select(ChittiPayout).where(
                ChittiPayout.chitti_id == UUID(chitti["id"]),
                ChittiPayout.period_number == 1,
            )
        )).scalars().all())
        assert len(payouts) == 1
        assert payouts[0].gross_payout == Decimal("1000.00")
        assert payouts[0].discount_amount == Decimal("100.00")
        assert payouts[0].fee_amount == Decimal("50.00")
        assert payouts[0].net_payout == Decimal("850.00")

        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
                ChittiTransaction.transaction_type == "PAYOUT",
                ChittiTransaction.period_number == 1,
            )
        )).scalars().all())
        assert len(ledger) == 1
        assert ledger[0].amount == Decimal("850.00")
        assert ledger[0].idempotency_key == "normal-payout-repeat"

        schedule = (
            await fresh.execute(
                select(ChittiPeriodSchedule).where(
                    ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
                    ChittiPeriodSchedule.period_number == 1,
                )
            )
        ).scalar_one()
        assert schedule.actual_payout == Decimal("850.00")

        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_PAYOUT_RECORDED")
        )).scalars().all())
        assert len(audit) == 1


@pytest.mark.asyncio
async def test_concurrent_payout_requests_create_one_payout(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    await db_session.commit()

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def payout(label: str):
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_payout(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    gross_payout=Decimal("1000"),
                    discount_amount=Decimal("100"),
                    fee_amount=Decimal("50"),
                    net_payout=Decimal("850"),
                    payout_method="CASH",
                    idempotency_key=f"concurrent-payout-{label}",
                    created_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(payout("a"), payout("b"))
    assert sum(isinstance(value, dict) for value in results) == 2
    assert sum(value.get("duplicate") is False for value in results if isinstance(value, dict)) == 1
    assert sum(value.get("duplicate") is True for value in results if isinstance(value, dict)) == 1

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        payouts = list((await fresh.execute(
            select(ChittiPayout).where(
                ChittiPayout.chitti_id == UUID(chitti["id"]),
                ChittiPayout.period_number == 1,
            )
        )).scalars().all())
        assert len(payouts) == 1

        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
                ChittiTransaction.transaction_type == "PAYOUT",
                ChittiTransaction.period_number == 1,
            )
        )).scalars().all())
        assert len(ledger) == 1

        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_PAYOUT_RECORDED")
        )).scalars().all())
        assert len(audit) == 1


@pytest.mark.asyncio
async def test_payout_invalid_amount_rejected_without_mutation(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)

    response = await client.post(
        f"/api/v1/chitti/{chitti['id']}/payouts",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "gross_payout": "1000.00",
            "discount_amount": "100.00",
            "fee_amount": "50.00",
            "net_payout": "849.99",
            "payout_method": "CASH",
            "idempotency_key": "invalid-payout-mismatch",
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PAYOUT_AMOUNT_MISMATCH"

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        payouts = list((await fresh.execute(
            select(ChittiPayout).where(ChittiPayout.chitti_id == UUID(chitti["id"]))
        )).scalars().all())
        assert payouts == []
        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
                ChittiTransaction.transaction_type == "PAYOUT",
            )
        )).scalars().all())
        assert ledger == []
        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_PAYOUT_RECORDED")
        )).scalars().all())
        assert audit == []


@pytest.mark.asyncio
async def test_payout_rolls_back_after_controlled_post_mutation_failure(
    client, test_user, test_engine, db_session, monkeypatch
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    await db_session.commit()

    async def fail_payout_ledger_create(self, **kwargs):
        raise RuntimeError("controlled payout rollback failure")

    from app.repositories.chitti_repo import ChittiTransactionRepository
    monkeypatch.setattr(
        ChittiTransactionRepository,
        "create",
        fail_payout_ledger_create,
    )

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        with pytest.raises(RuntimeError, match="controlled payout rollback"):
            await ChittiService(session).record_payout(
                UUID(chitti["id"]),
                member_id=members[0]["id"],
                period_number=1,
                gross_payout=Decimal("1000"),
                discount_amount=Decimal("100"),
                fee_amount=Decimal("50"),
                net_payout=Decimal("850"),
                payout_method="CASH",
                idempotency_key="rollback-payout",
                created_by=test_user["user"].id,
            )
        await session.rollback()

    monkeypatch.undo()

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        payouts = list((await fresh.execute(
            select(ChittiPayout).where(ChittiPayout.chitti_id == UUID(chitti["id"]))
        )).scalars().all())
        assert payouts == []

        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
                ChittiTransaction.transaction_type == "PAYOUT",
            )
        )).scalars().all())
        assert ledger == []

        schedule = (
            await fresh.execute(
                select(ChittiPeriodSchedule).where(
                    ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
                    ChittiPeriodSchedule.period_number == 1,
                )
            )
        ).scalar_one()
        assert schedule.actual_payout == Decimal("0")

        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_PAYOUT_RECORDED")
        )).scalars().all())
        assert audit == []


@pytest.mark.asyncio
async def test_payout_concurrent_with_contribution_preserves_totals(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    await db_session.commit()
    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def payout():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_payout(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    gross_payout=Decimal("1000"),
                    discount_amount=Decimal("100"),
                    fee_amount=Decimal("50"),
                    net_payout=Decimal("850"),
                    payout_method="CASH",
                    idempotency_key="payout-vs-contribution",
                    created_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    async def contribution():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_contribution(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    amount=Decimal("400"),
                    payment_method="UPI",
                    payment_date=date.today(),
                    idempotency_key="payout-vs-contribution-400",
                    created_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(payout(), contribution())
    assert all(isinstance(value, dict) for value in results)

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        payout_rows = list((await fresh.execute(
            select(ChittiPayout).where(ChittiPayout.chitti_id == UUID(chitti["id"]))
        )).scalars().all())
        assert len(payout_rows) == 1
        assert payout_rows[0].net_payout == Decimal("850")

        schedule = (
            await fresh.execute(
                select(ChittiPeriodSchedule).where(
                    ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
                    ChittiPeriodSchedule.period_number == 1,
                )
            )
        ).scalar_one()
        assert schedule.actual_collection == Decimal("400")
        assert schedule.pending_collection == Decimal("600")
        assert schedule.actual_payout == Decimal("850")

        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
            )
        )).scalars().all())
        assert sum(row.transaction_type == "CONTRIBUTION" for row in ledger) == 1
        assert sum(row.transaction_type == "PAYOUT" for row in ledger) == 1


@pytest.mark.asyncio
async def test_payout_concurrent_with_reversal_preserves_totals(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    contribution = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "400.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "payout-vs-reversal-origin",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
    transaction_id = contribution.json()["data"]["transaction_id"]
    await db_session.commit()

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def payout():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_payout(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    gross_payout=Decimal("1000"),
                    discount_amount=Decimal("100"),
                    fee_amount=Decimal("50"),
                    net_payout=Decimal("850"),
                    payout_method="CASH",
                    idempotency_key="payout-vs-reversal-payout",
                    created_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    async def reversal():
        async with sessions() as session:
            try:
                result = await ChittiService(session).reverse_contribution(
                    UUID(chitti["id"]),
                    UUID(transaction_id),
                    reason="payout reversal race",
                    reversed_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(payout(), reversal())
    assert all(isinstance(value, dict) for value in results)

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        contribution_row = (
            await fresh.execute(
                select(ChittiMemberContribution).where(
                    ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                    ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                    ChittiMemberContribution.period_number == 1,
                )
            )
        ).scalar_one()
        assert contribution_row.paid_amount == Decimal("0")
        assert contribution_row.remaining_amount == Decimal("1000")

        payout_rows = list((await fresh.execute(
            select(ChittiPayout).where(ChittiPayout.chitti_id == UUID(chitti["id"]))
        )).scalars().all())
        assert len(payout_rows) == 1
        assert payout_rows[0].net_payout == Decimal("850")

        schedule = (
            await fresh.execute(
                select(ChittiPeriodSchedule).where(
                    ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
                    ChittiPeriodSchedule.period_number == 1,
                )
            )
        ).scalar_one()
        assert schedule.actual_payout == Decimal("850")
        assert schedule.actual_collection == Decimal("0")
        assert schedule.pending_collection == Decimal("1000")

        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
            )
        )).scalars().all())
        assert sum(row.transaction_type == "CONTRIBUTION" for row in ledger) == 1
        assert sum(row.transaction_type == "PAYOUT" for row in ledger) == 1
        assert sum(row.transaction_type == "REVERSAL" for row in ledger) <= 1


@pytest.mark.asyncio
async def test_normal_and_repeated_lift_requests(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    plan = (
        await client.post("/api/v1/chitti/plans", json={
            "name": "P0.3 Lift Plan",
            "chitti_type": "LIFT_BASED",
            "total_value": "120000.00",
            "member_count": 1,
            "frequency": "DAILY",
            "duration": 4,
            "contribution_rules": {
                "type": "LIFT_BASED",
                "regular_amount": "5000.00",
            },
            "payout_rules": {
                "type": "SCHEDULED",
                "payout_order": "MEMBER_NUMBER",
            },
        }, headers=headers)
    ).json()["data"]
    chitti = (
        await client.post("/api/v1/chitti/", json={
            "plan_id": plan["id"],
            "name": "P0.3 Lift Chitti",
            "member_count": 1,
            "start_date": date.today().isoformat(),
        }, headers=headers)
    ).json()["data"]
    customer = await _customer(client, headers, 1)
    member = (
        await client.post(
            f"/api/v1/chitti/{chitti['id']}/members",
            json={"customer_id": customer["id"], "payout_order": 1},
            headers=headers,
        )
    ).json()["data"]
    await _activate_member(client, headers, chitti["id"], member["id"])
    started = await client.post(f"/api/v1/chitti/{chitti['id']}/start", headers=headers)
    assert started.status_code == 200, started.text

    first = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts",
        json={
            "member_id": member["id"],
            "period_number": 1,
            "lift_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert first.status_code == 200, first.text
    lift_id = first.json()["data"]["id"]
    await db_session.commit()

    repeated = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts",
        json={
            "member_id": member["id"],
            "period_number": 1,
            "lift_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert repeated.status_code == 409

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        lift_events = list((await fresh.execute(
            select(ChittiLiftEvent).where(
                ChittiLiftEvent.chitti_id == UUID(chitti["id"]),
                ChittiLiftEvent.reversed_at.is_(None),
            )
        )).scalars().all())
        assert len(lift_events) == 1
        assert str(lift_events[0].id) == lift_id

        member_row = (
            await fresh.execute(
                select(ChittiMember).where(
                    ChittiMember.chitti_id == UUID(chitti["id"]),
                    ChittiMember.id == UUID(member["id"]),
                )
            )
        ).scalar_one()
        assert member_row.lifted is True
        assert member_row.lift_period == 1

        contributions = list((await fresh.execute(
            select(ChittiMemberContribution).where(
                ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                ChittiMemberContribution.member_id == UUID(member["id"]),
            )
        )).scalars().all())
        assert [row.expected_amount for row in contributions] == [
            Decimal("5000"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]
        assert sum(row.expected_amount for row in contributions) == Decimal("23600")

        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_LIFT_RECORDED")
        )).scalars().all())
        assert len(audit) == 1

        schedules = list((await fresh.execute(
            select(ChittiPeriodSchedule).where(
                ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
            ).order_by(ChittiPeriodSchedule.period_number)
        )).scalars().all())
        assert [row.expected_collection for row in schedules] == [
            Decimal("5000"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]
        assert all(row.pending_collection == row.expected_collection for row in schedules)


@pytest.mark.asyncio
async def test_concurrent_lift_requests(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_lift_chitti(client, headers, member_count=2)
    await db_session.commit()
    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def lift(member_id: str, period_number: int):
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_lift(
                    UUID(chitti["id"]),
                    member_id=member_id,
                    period_number=period_number,
                    lift_date=date.today(),
                    recorded_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    same_member = await asyncio.gather(
        lift(members[0]["id"], 1),
        lift(members[0]["id"], 1),
    )
    assert sum(isinstance(value, dict) for value in same_member) == 1
    assert sum(isinstance(value, Exception) for value in same_member) == 1

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        active = list((await fresh.execute(
            select(ChittiLiftEvent).where(
                ChittiLiftEvent.chitti_id == UUID(chitti["id"]),
                ChittiLiftEvent.reversed_at.is_(None),
            )
        )).scalars().all())
        assert len(active) == 1

    different_members = await asyncio.gather(
        lift(members[0]["id"], 2),
        lift(members[1]["id"], 2),
    )
    assert sum(isinstance(value, Exception) for value in different_members) >= 1

    async with fresh_sessions() as fresh:
        active = list((await fresh.execute(
            select(ChittiLiftEvent).where(
                ChittiLiftEvent.chitti_id == UUID(chitti["id"]),
                ChittiLiftEvent.reversed_at.is_(None),
            )
        )).scalars().all())
        assert len(active) <= 2


@pytest.mark.asyncio
async def test_lift_rolls_back_after_controlled_post_mutation_failure(
    client, test_user, test_engine, db_session, monkeypatch
):
    headers = _auth(test_user)
    chitti, members = await _running_lift_chitti(client, headers, member_count=1)
    await db_session.commit()

    async def fail_lift_audit(self, **kwargs):
        raise RuntimeError("controlled lift rollback failure")

    monkeypatch.setattr(
        AuditLogRepository,
        "log",
        fail_lift_audit,
    )

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        with pytest.raises(RuntimeError, match="controlled lift rollback"):
            await ChittiService(session).record_lift(
                UUID(chitti["id"]),
                member_id=members[0]["id"],
                period_number=1,
                lift_date=date.today(),
                recorded_by=test_user["user"].id,
            )
        await session.rollback()

    monkeypatch.undo()

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        lift_events = list((await fresh.execute(
            select(ChittiLiftEvent).where(
                ChittiLiftEvent.chitti_id == UUID(chitti["id"]),
            )
        )).scalars().all())
        assert lift_events == []

        member_row = (
            await fresh.execute(
                select(ChittiMember).where(
                    ChittiMember.chitti_id == UUID(chitti["id"]),
                    ChittiMember.id == UUID(members[0]["id"]),
                )
            )
        ).scalar_one()
        assert member_row.lifted is False
        assert member_row.lift_period is None

        contributions = list((await fresh.execute(
            select(ChittiMemberContribution).where(
                ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                ChittiMemberContribution.member_id == UUID(members[0]["id"]),
            )
        )).scalars().all())
        assert len(contributions) == 4
        assert [row.expected_amount for row in contributions] == [
            Decimal("5000"),
            Decimal("5000"),
            Decimal("5000"),
            Decimal("5000"),
        ]

        audit = list((await fresh.execute(
            select(AuditLog).where(AuditLog.action == "CHITTI_LIFT_RECORDED")
        )).scalars().all())
        assert audit == []


@pytest.mark.asyncio
async def test_lift_concurrent_with_collection_preserves_totals(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_lift_chitti(client, headers, member_count=1)
    await db_session.commit()
    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def lift():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_lift(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    lift_date=date.today(),
                    recorded_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    async def collect():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_contribution(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    amount=Decimal("5000"),
                    payment_method="CASH",
                    payment_date=date.today(),
                    idempotency_key="lift-vs-contribution-5000",
                    created_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(lift(), collect())
    assert all(isinstance(value, dict) for value in results)

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        member_row = (
            await fresh.execute(
                select(ChittiMember).where(
                    ChittiMember.chitti_id == UUID(chitti["id"]),
                    ChittiMember.id == UUID(members[0]["id"]),
                )
            )
        ).scalar_one()

        contribution = (
            await fresh.execute(
                select(ChittiMemberContribution).where(
                    ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                    ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                    ChittiMemberContribution.period_number == 1,
                )
            )
        ).scalar_one()

        if member_row.lifted:
            assert contribution.expected_amount == Decimal("5000")
            assert contribution.paid_amount == Decimal("5000")
            assert member_row.lift_period == 1
        else:
            assert member_row.lift_period is None
            assert contribution.paid_amount == Decimal("5000")


@pytest.mark.asyncio
async def test_lift_paid_before_lift_recalculates_member_and_period_totals(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_lift_chitti(client, headers, member_count=1)
    contribution = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "5000.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "paid-before-lift-period-one",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
    assert contribution.json()["data"]["duplicate"] is False
    await db_session.commit()

    lift = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "lift_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert lift.status_code == 200, lift.text
    await db_session.commit()

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        member_row = (
            await fresh.execute(
                select(ChittiMember).where(
                    ChittiMember.chitti_id == UUID(chitti["id"]),
                    ChittiMember.id == UUID(members[0]["id"]),
                )
            )
        ).scalar_one()
        assert member_row.lifted is True
        assert member_row.lift_period == 1
        assert member_row.total_paid_amount == Decimal("5000")

        contributions = list((await fresh.execute(
            select(ChittiMemberContribution).where(
                ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                ChittiMemberContribution.member_id == UUID(members[0]["id"]),
            ).order_by(ChittiMemberContribution.period_number)
        )).scalars().all())
        assert [row.expected_amount for row in contributions] == [
            Decimal("5000"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]
        assert [row.paid_amount for row in contributions] == [
            Decimal("5000"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        ]
        assert [row.remaining_amount for row in contributions] == [
            Decimal("0"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]
        assert sum(row.expected_amount for row in contributions) == Decimal("23600")
        assert sum(row.paid_amount for row in contributions) == Decimal("5000")
        assert sum(row.remaining_amount for row in contributions) == Decimal("18600")
        assert member_row.total_expected_amount == Decimal("23600")
        assert member_row.outstanding_amount == Decimal("18600")

        schedules = list((await fresh.execute(
            select(ChittiPeriodSchedule).where(
                ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
            ).order_by(ChittiPeriodSchedule.period_number)
        )).scalars().all())
        assert [row.expected_collection for row in schedules] == [
            Decimal("5000"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]
        assert [row.actual_collection for row in schedules] == [
            Decimal("5000"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        ]
        assert [row.pending_collection for row in schedules] == [
            Decimal("0"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]


@pytest.mark.asyncio
async def test_lift_concurrent_with_contribution_reversal_preserves_totals(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_lift_chitti(client, headers, member_count=1)
    contribution = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "5000.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "lift-vs-reversal-origin",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
    transaction_id = contribution.json()["data"]["transaction_id"]
    await db_session.commit()

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def lift():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_lift(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    lift_date=date.today(),
                    recorded_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    async def reverse():
        async with sessions() as session:
            try:
                result = await ChittiService(session).reverse_contribution(
                    UUID(chitti["id"]),
                    UUID(transaction_id),
                    reason="lift reversal race",
                    reversed_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(lift(), reverse())
    assert all(isinstance(value, dict) for value in results)

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        contributions = list((await fresh.execute(
            select(ChittiMemberContribution).where(
                ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                ChittiMemberContribution.member_id == UUID(members[0]["id"]),
            )
        )).scalars().all())
        assert [row.expected_amount for row in contributions] == [
            Decimal("5000"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]
        assert [row.paid_amount for row in contributions] == [
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        ]
        assert [row.remaining_amount for row in contributions] == [
            Decimal("5000"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]
        assert sum(row.expected_amount for row in contributions) == Decimal("23600")
        assert sum(row.paid_amount for row in contributions) == Decimal("0")
        assert sum(row.remaining_amount for row in contributions) == Decimal("23600")

        schedules = list((await fresh.execute(
            select(ChittiPeriodSchedule).where(
                ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
            ).order_by(ChittiPeriodSchedule.period_number)
        )).scalars().all())
        assert [row.expected_collection for row in schedules] == [
            Decimal("5000"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]
        assert [row.actual_collection for row in schedules] == [
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        ]
        assert [row.pending_collection for row in schedules] == [
            Decimal("5000"),
            Decimal("6200"),
            Decimal("6200"),
            Decimal("6200"),
        ]

        ledger = list((await fresh.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == UUID(chitti["id"]),
                ChittiTransaction.period_number == 1,
            )
        )).scalars().all())
        assert sum(row.transaction_type == "CONTRIBUTION" for row in ledger) == 1
        assert sum(row.transaction_type == "REVERSAL" for row in ledger) == 1


@pytest.mark.asyncio
async def test_lift_concurrent_with_payout_preserves_totals(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_lift_chitti(client, headers, member_count=1)
    await db_session.commit()
    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def lift():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_lift(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    lift_date=date.today(),
                    recorded_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    async def payout():
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_payout(
                    UUID(chitti["id"]),
                    member_id=members[0]["id"],
                    period_number=1,
                    gross_payout=Decimal("1000"),
                    discount_amount=Decimal("0"),
                    fee_amount=Decimal("0"),
                    net_payout=Decimal("1000"),
                    payout_method="CASH",
                    idempotency_key="lift-vs-payout",
                    created_by=test_user["user"].id,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(lift(), payout())
    assert all(isinstance(value, dict) for value in results)

    fresh_sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with fresh_sessions() as fresh:
        payouts = list((await fresh.execute(
            select(ChittiPayout).where(
                ChittiPayout.chitti_id == UUID(chitti["id"]),
                ChittiPayout.period_number == 1,
            )
        )).scalars().all())
        assert len(payouts) == 1
        assert payouts[0].net_payout == Decimal("1000")

        schedule = (
            await fresh.execute(
                select(ChittiPeriodSchedule).where(
                    ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
                    ChittiPeriodSchedule.period_number == 1,
                )
            )
        ).scalar_one()
        assert schedule.actual_payout == Decimal("1000")


@pytest.mark.asyncio
async def test_daily_report_separates_and_totals_both_ledgers(client, test_user):
    headers = _auth(test_user)
    today = date.today().isoformat()

    chitti, members = await _running_chitti(client, headers, members=2)

    # ---- A chitti contribution is collected with NO finance account ----------
    body = {
        "member_id": members[0]["id"],
        "period_number": 1,
        "amount": "500.00",
        "payment_method": "CASH",
        "payment_date": today,
        "idempotency_key": "report-consistency-chitti-1",
    }
    first = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions", json=body, headers=headers
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["duplicate"] is False

    retried = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions", json=body, headers=headers
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["data"]["duplicate"] is True, "retry must not double-count"

    # The same key must not be usable for a different amount (that is a client
    # bug, not a retry, and must never move money silently).
    reused = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={**body, "amount": "100.00"},
        headers=headers,
    )
    assert reused.status_code == 400, reused.text
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    # ---- A finance installment is collected on its own account --------------
    customer = members[0]["customer_id"]
    account = await client.post(
        "/api/v1/finance/",
        json={
            "customer_id": customer,
            "principal_amount": "3000.00",
            "interest_rate": "0",
            "interest_type": "FLAT",
            "fees": "0",
            "frequency": "WEEKLY",
            "start_date": today,
            "first_due_date": today,
            "number_of_installments": 3,
        },
        headers=headers,
    )
    assert account.status_code == 200, account.text
    account_id = account.json()["data"]["id"]

    schedule = await client.get(f"/api/v1/finance/{account_id}/schedule", headers=headers)
    assert schedule.status_code == 200, schedule.text
    first_installment = next(
        s for s in schedule.json()["data"] if s["due_date"] == today
    )

    paid = await client.post(
        "/api/v1/payments/",
        json={
            "customer_id": customer,
            "finance_account_id": account_id,
            "finance_schedule_id": first_installment["id"],
            "amount": "300.00",
            "payment_method": "UPI",
            "payment_date": today,
            "idempotency_key": "report-consistency-finance-1",
        },
        headers=headers,
    )
    assert paid.status_code == 200, paid.text

    # ---- The daily report must show both streams, correctly split ----------
    before = (
        await client.get(f"/api/v1/reports/daily?date={today}", headers=headers)
    ).json()["data"]

    assert before["chitti_collected"] == 500.0
    assert before["finance_collected"] == 300.0
    assert before["collected_total"] == 800.0
    assert before["net_collections"] == 800.0
    assert before["finance_pending"] == float(first_installment["expected_amount"]) - 300.0
    assert before["chitti_pending"] > 0

    pending_items = before["pending_details"]
    pending_sum = sum(float(item["pending"]) for item in pending_items)
    assert math.isclose(before["pending_total"], pending_sum, abs_tol=0.01), (
        "headline pending must equal the drill-down it shows"
    )
    assert math.isclose(
        before["pending_total"],
        float(before["finance_pending"]) + float(before["chitti_pending"]),
        abs_tol=0.01,
    )

    # The chitti drill-down names the member, not the chitti as a customer.
    chitti_items = [i for i in pending_items if i["source"] == "CHITTI"]
    assert chitti_items, "chitti dues must appear in the pending drill-down"
    for item in chitti_items:
        assert item["customer_id"]
        assert item["customer_name"] and item["customer_name"] != "Report Chitti"
        assert item["mobile_number"]

    # Every payment of the day is listed with its source.
    sources = {p["source"] for p in before["payments"]}
    assert sources == {"CHITTI", "FINANCE"}
    assert sorted(float(p["amount"]) for p in before["payments"]) == [300.0, 500.0]

    # Analytics must agree with the report about chitti money.
    analytics = (
        await client.get("/api/v1/analytics/chitti/overview", headers=headers)
    ).json()["data"]
    assert analytics["kpis"]["total_collected"] == 500.0

    # ---- A DRAFT chitti must not invent dues -------------------------------
    plans = (await client.get("/api/v1/chitti/plans", headers=headers)).json()["data"]
    draft = await client.post(
        "/api/v1/chitti/",
        json={
            "plan_id": plans[0]["id"],
            "name": "Draft Report Chitti",
            "start_date": today,
            "member_count": 4,
        },
        headers=headers,
    )
    assert draft.status_code == 200, draft.text

    after = (
        await client.get(f"/api/v1/reports/daily?date={today}", headers=headers)
    ).json()["data"]
    assert after["expected_total"] == before["expected_total"]
    assert after["pending_total"] == before["pending_total"]
    assert after["chitti_expected"] == before["chitti_expected"]


@pytest.mark.asyncio
async def test_range_csv_and_xlsx_match_json_report(client, test_user):
    """Download formats contain the same ledger rows and totals as the UI API."""
    headers = _auth(test_user)
    today = date.today().isoformat()
    chitti, members = await _running_chitti(client, headers, members=1)
    payment = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": members[0]["id"],
            "period_number": 1,
            "amount": "1000.00",
            "payment_method": "UPI",
            "payment_date": today,
            "idempotency_key": "range-export-chitti-payment",
        },
        headers=headers,
    )
    assert payment.status_code == 200, payment.text

    params = {"start_date": today, "end_date": today, "report_type": "chitti"}
    report = (await client.get("/api/v1/reports/range", params=params, headers=headers)).json()["data"]
    assert report["chitti_collected"] == 1000.0
    assert len(report["transactions"]) == 1

    csv_response = await client.get(
        "/api/v1/reports/range/export",
        params={**params, "file_format": "csv"},
        headers=headers,
    )
    assert csv_response.status_code == 200, csv_response.text
    csv_rows = list(csv.DictReader(StringIO(csv_response.content.decode("utf-8-sig"))))
    summary = next(row for row in csv_rows if row["record_type"] == "SUMMARY")
    transaction_rows = [row for row in csv_rows if row["record_type"] == "TRANSACTION"]
    assert float(summary["chitti_collected"]) == report["chitti_collected"]
    assert len(transaction_rows) == len(report["transactions"])
    assert transaction_rows[0]["source"] == report["transactions"][0]["source"] == "CHITTI"

    xlsx_response = await client.get(
        "/api/v1/reports/range/export",
        params={**params, "file_format": "xlsx"},
        headers=headers,
    )
    assert xlsx_response.status_code == 200, xlsx_response.text
    workbook = load_workbook(BytesIO(xlsx_response.content), read_only=True, data_only=True)
    summary_values = {row[0]: row[1] for row in workbook["Summary"].iter_rows(values_only=True)}
    assert float(summary_values["chitti_collected"]) == report["chitti_collected"]
    xlsx_transactions = list(workbook["Transactions"].iter_rows(values_only=True))
    assert len(xlsx_transactions) == len(report["transactions"]) + 1
    assert workbook["Pending dues"].max_row >= 1

    collector_params = {**params, "report_type": "collector"}
    collector_report = (await client.get(
        "/api/v1/reports/range", params=collector_params, headers=headers
    )).json()["data"]
    assert len(collector_report["breakdown"]) == 1
    assert collector_report["breakdown"][0]["transaction_count"] == 1
    assert collector_report["breakdown"][0]["chitti_collected"] == 1000.0
    collector_csv = await client.get(
        "/api/v1/reports/range/export",
        params={**collector_params, "file_format": "csv"}, headers=headers,
    )
    csv_breakdown = list(csv.DictReader(StringIO(collector_csv.content.decode("utf-8-sig"))))
    breakdown_row = next(row for row in csv_breakdown if row["record_type"] == "BREAKDOWN")
    assert float(breakdown_row["chitti_collected"]) == collector_report["breakdown"][0]["chitti_collected"]
