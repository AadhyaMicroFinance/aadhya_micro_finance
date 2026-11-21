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
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.models.audit import AuditLog
from app.models.payment import PaymentTransaction
from app.models.chitti import (
    Chitti,
    ChittiMember,
    ChittiMemberContribution,
    ChittiPeriodSchedule,
    ChittiPayout,
    ChittiTransaction,
    ChittiLiftEvent,
    ChittiPaymentAllocation,
)
from app.core.exceptions import BadRequestException
from app.repositories.chitti_repo import ChittiTransactionRepository
from app.repositories.audit_repo import AuditLogRepository
from app.services.analytics_service import ChittiAnalyticsService
from app.services.chitti_service import ChittiService
from app.services.chitti_financial_values import aggregate_period_values
from app.services.report_service import ReportService
from app.utils.timezone import today_ist
from tests.finance_helpers import create_finance_account

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


async def _reversal_headers(db_session):
    """Payment reversal requires an explicit elevated permission."""
    from app.core.security import create_access_token
    from app.models.user import User

    user = User(
        id=uuid4(),
        username=f"reversal-admin-{uuid4().hex[:6]}",
        email=f"reversal-admin-{uuid4().hex[:6]}@test.com",
        password_hash="x",
        full_name="Reversal Admin",
        role="SUPER_ADMIN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def test_legacy_period_values_fall_back_to_schedule_and_reconcile_pending():
    chitti_id = UUID(int=1)
    schedule = SimpleNamespace(
        chitti_id=chitti_id,
        period_number=1,
        expected_collection=Decimal("100"),
        actual_collection=Decimal("25"),
        pending_collection=Decimal("90"),
    )

    values = aggregate_period_values([schedule], [], {})

    assert values[(chitti_id, 1)] == {
        "expected": Decimal("100"),
        "paid": Decimal("25"),
        "pending": Decimal("75"),
    }


@pytest.mark.parametrize(
    ("expected", "paid", "due_date", "status"),
    [
        (Decimal("100"), Decimal("40"), None, "PARTIALLY_PAID"),
        (Decimal("100"), Decimal("100"), None, "PAID"),
        (Decimal("100"), Decimal("150"), None, "ADVANCE_PAID"),
        (Decimal("0"), Decimal("10"), None, "ADVANCE_PAID"),
    ],
)
def test_analytics_contribution_state_respects_effective_amounts(
    expected, paid, due_date, status
):
    contribution = SimpleNamespace(
        expected_amount=expected,
        paid_amount=paid,
    )

    assert ChittiAnalyticsService._contribution_state(
        contribution,
        due_date,
        date.today(),
        effective_expected=expected,
    ) == status


@pytest.mark.asyncio
async def test_pending_report_ignores_stale_paid_status():
    due_date = today_ist()
    contribution = SimpleNamespace(
        id=UUID(int=1),
        chitti_id=UUID(int=2),
        period_number=1,
        status="PAID",
    )
    pending_row = SimpleNamespace(
        ChittiMemberContribution=contribution,
        due_date=due_date,
        chitti_code="CHT-TEST",
        customer_id=UUID(int=3),
        full_name="Test Member",
        customer_code="CUS-TEST",
        mobile_number="9000000000",
        chitti_name="Test Chitti",
        member_number=1,
        member_alias="Slot A",
    )

    class FakeSession:
        def __init__(self):
            self.calls = 0

        async def execute(self, statement):
            self.calls += 1
            rows = [] if self.calls == 1 else [pending_row]
            return SimpleNamespace(all=lambda: rows)

    service = ReportService(FakeSession())

    async def effective_value(_):
        return {
            "expected": Decimal("100"),
            "paid": Decimal("0"),
            "remaining": Decimal("100"),
        }

    service._effective_contribution_value = effective_value
    result = await service.get_pending_details(report_date=due_date)

    assert len(result) == 1
    assert result[0]["pending"] == Decimal("100")
    assert result[0]["status"] == "PENDING"
    assert result[0]["member_number"] == 1
    assert result[0]["member_alias"] == "Slot A"


@pytest.mark.asyncio
async def test_contribution_idempotency_key_cannot_match_payout_transaction():
    chitti_id = UUID(int=1)
    member_id = UUID(int=2)
    contribution = SimpleNamespace(id=UUID(int=3))
    payout = SimpleNamespace(
        id=UUID(int=4),
        chitti_id=chitti_id,
        transaction_type="PAYOUT",
        member_id=member_id,
        period_number=1,
        amount=Decimal("100"),
    )
    service = object.__new__(ChittiService)
    service.chitti_repo = SimpleNamespace(
        get_by_id_for_update=AsyncMock(
            return_value=SimpleNamespace(id=chitti_id, status="RUNNING")
        )
    )
    service.member_repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(id=member_id, chitti_id=chitti_id)
        ),
        get_by_id_for_update=AsyncMock(
            return_value=SimpleNamespace(id=member_id, chitti_id=chitti_id)
        ),
    )
    service.contribution_repo = SimpleNamespace(
        get_by_chitti_member_period_for_update=AsyncMock(
            return_value=contribution
        )
    )
    service.txn_repo = SimpleNamespace(
        get_by_idempotency_key=AsyncMock(return_value=payout)
    )

    with pytest.raises(BadRequestException) as exc:
        await service.record_contribution(
            chitti_id,
            member_id=str(member_id),
            period_number=1,
            amount=Decimal("100"),
            payment_method="CASH",
            payment_date=date.today(),
            idempotency_key="payout-key-reused-as-contribution",
        )

    assert exc.value.error_code == "IDEMPOTENCY_KEY_REUSED"
    service.txn_repo.get_by_idempotency_key.assert_awaited_once()


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
                "member_count": members,
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
async def test_lift_recalculation_does_not_create_or_move_credit(
    client, test_user, db_session
):
    """A lift changes expectations only; credit needs an operator decision."""
    headers = _auth(test_user)
    chitti, members = await _running_lift_chitti(client, headers, member_count=1)
    member_id = members[0]["id"]
    payment = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": member_id,
            "period_number": 1,
            "amount": "25000.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "lift-credit-allocation-payment",
        },
        headers=headers,
    )
    assert payment.status_code == 200, payment.text
    transaction_id = payment.json()["data"]["transaction_id"]
    assert payment.json()["data"]["unallocated_credit"] == 0.0
    assert payment.json()["data"]["unresolved_excess"] == 5000.0

    allocations = list((await db_session.execute(
        select(ChittiPaymentAllocation).where(
            ChittiPaymentAllocation.source_transaction_id == UUID(transaction_id)
        )
    )).scalars().all())
    by_type = {}
    for row in allocations:
        by_type[row.allocation_type] = by_type.get(row.allocation_type, Decimal("0")) + row.amount
    assert by_type.get("CONTRIBUTION") == Decimal("20000.00")
    assert by_type.get("UNRESOLVED") == Decimal("5000.00")
    assert "CREDIT" not in by_type

    lift = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts",
        json={
            "member_id": member_id,
            "period_number": 1,
            "lift_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert lift.status_code == 200, lift.text

    member_data = next(
        row for row in (
            await client.get(
                f"/api/v1/chitti/{chitti['id']}/members", headers=headers
            )
        ).json()["data"]
        if row["id"] == member_id
    )
    assert member_data["total_expected"] == 23600
    assert member_data["total_paid"] == 20000
    assert member_data["unallocated_credit"] == 0
    assert member_data["unresolved_excess"] == 5000
    assert member_data["outstanding"] == 3600

    schedule = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/schedule", headers=headers
    )).json()["data"]
    assert sum(row["expected_collection"] for row in schedule) == 23600
    assert sum(row["actual_collection"] for row in schedule) == 20000
    assert sum(row["pending_collection"] for row in schedule) == 3600

    after = list((await db_session.execute(
        select(ChittiPaymentAllocation).where(
            ChittiPaymentAllocation.source_transaction_id == UUID(transaction_id)
        )
    )).scalars().all())
    assert len(after) == len(allocations)


@pytest.mark.asyncio
async def test_reversal_restores_schedule_and_report(client, test_user, db_session):
    """A reversed payment must free the installment again and net out."""
    headers = _auth(test_user)
    today = date.today().isoformat()
    customer = await _customer(client, headers, 7)

    account, _ = await create_finance_account(
        client,
        headers,
        customer["id"],
        frequency="WEEKLY",
        number_of_installments=3,
    )

    schedule = (
        await client.get(f"/api/v1/finance/{account['id']}/schedule", headers=headers)
    ).json()["data"]
    installment = next(s for s in schedule if s["due_date"] == today)

    # Chitti fields are not part of the Finance payment contract at all.
    # Rejecting at the schema boundary keeps module ledgers structurally separate.
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
    assert blocked.status_code == 422, blocked.text
    assert "chitti_account_id" in blocked.text
    assert (await db_session.scalar(select(func.count()).select_from(PaymentTransaction))) == 0

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

    reversal_headers = await _reversal_headers(db_session)
    reversal = await client.post(
        f"/api/v1/payments/{payment['id']}/reverse",
        json={"reversal_reason": "cash returned"},
        headers=reversal_headers,
    )
    assert reversal.status_code == 200, reversal.text

    # Retrying the same reversal must replay the first ledger row, not fail
    # on its idempotency key or restore the installment twice.
    replay = await client.post(
        f"/api/v1/payments/{payment['id']}/reverse",
        json={"reversal_reason": "cash returned"},
        headers=reversal_headers,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["id"] == reversal.json()["data"]["id"]

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

    reversal_headers = await _reversal_headers(db_session)
    reversal = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{original_id}/reverse",
        json={"reversal_reason": "regression reversal"}, headers=reversal_headers,
    )
    assert reversal.status_code == 200, reversal.text
    assert reversal.json()["data"]["duplicate"] is False
    repeated = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{original_id}/reverse",
        json={"reversal_reason": "retry"}, headers=reversal_headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["duplicate"] is True

    reversal_rows = list((await db_session.execute(
        select(ChittiTransaction).where(
            ChittiTransaction.chitti_id == UUID(chitti["id"]),
            ChittiTransaction.transaction_type == "REVERSAL",
        )
    )).scalars().all())
    assert len(reversal_rows) == 1
    assert reversal_rows[0].original_transaction_id == UUID(original_id)

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
async def test_normal_contribution_duplicate_creates_one_audit_entry(
    client, test_user, db_session
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    body = {
        "member_id": members[0]["id"],
        "period_number": 1,
        "amount": "400.00",
        "payment_method": "CASH",
        "payment_date": date.today().isoformat(),
        "idempotency_key": "normal-contribution-audit",
    }

    first = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json=body,
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["duplicate"] is False

    contribution = (
        await db_session.execute(
            select(ChittiMemberContribution).where(
                ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                ChittiMemberContribution.period_number == 1,
            )
        )
    ).scalar_one()
    member = (
        await db_session.execute(
            select(ChittiMember).where(ChittiMember.id == UUID(members[0]["id"]))
        )
    ).scalar_one()
    schedule = (
        await db_session.execute(
            select(ChittiPeriodSchedule).where(
                ChittiPeriodSchedule.chitti_id == UUID(chitti["id"]),
                ChittiPeriodSchedule.period_number == 1,
            )
        )
    ).scalar_one()
    contribution.expected_amount = Decimal("1250.00")
    contribution.remaining_amount = Decimal("850.00")
    contribution.status = "PARTIALLY_PAID"
    member.total_expected_amount = Decimal("4321.00")
    member.total_paid_amount = Decimal("432.00")
    member.outstanding_amount = Decimal("3889.00")
    schedule.expected_collection = Decimal("9999.00")
    schedule.actual_collection = Decimal("7777.00")
    schedule.pending_collection = Decimal("2222.00")
    await db_session.flush()
    before_retry = (
        contribution.expected_amount,
        contribution.remaining_amount,
        contribution.status,
        member.total_expected_amount,
        member.total_paid_amount,
        member.outstanding_amount,
        schedule.expected_collection,
        schedule.actual_collection,
        schedule.pending_collection,
    )

    repeated = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json=body,
        headers=headers,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["data"]["duplicate"] is True
    after_retry = (
        contribution.expected_amount,
        contribution.remaining_amount,
        contribution.status,
        member.total_expected_amount,
        member.total_paid_amount,
        member.outstanding_amount,
        schedule.expected_collection,
        schedule.actual_collection,
        schedule.pending_collection,
    )
    assert after_retry == before_retry

    transaction_id = UUID(first.json()["data"]["transaction_id"])
    transaction = (
        await db_session.execute(
            select(ChittiTransaction).where(ChittiTransaction.id == transaction_id)
        )
    ).scalar_one()
    assert transaction.idempotency_key == body["idempotency_key"]
    assert transaction.amount == Decimal(body["amount"])
    audit_entries = list((await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "CHITTI_CONTRIBUTION_RECORDED",
            AuditLog.entity_id == transaction_id,
        )
    )).scalars().all())
    assert len(audit_entries) == 1
    payload = audit_entries[0].new_value
    assert payload["chitti_id"] == chitti["id"]
    assert payload["member_id"] == members[0]["id"]
    assert payload["transaction_id"] == str(transaction_id)
    assert payload["contribution_id"] == first.json()["data"]["contribution_id"]
    assert payload["period_number"] == 1
    assert payload["amount"] == "400.00"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("paid", "expected_outstanding"),
    [
        (Decimal("100"), 0.0),
        (Decimal("40"), 60.0),
        (Decimal("150"), 0.0),
    ],
)
async def test_member_detail_outstanding_is_clamped_without_losing_overpayment(
    client, test_user, db_session, paid, expected_outstanding
):
    headers = _auth(test_user)
    chitti, members = await _running_chitti(client, headers, members=1)
    contributions = list(
        (
            await db_session.execute(
                select(ChittiMemberContribution)
                .where(
                    ChittiMemberContribution.chitti_id == UUID(chitti["id"]),
                    ChittiMemberContribution.member_id == UUID(members[0]["id"]),
                )
                .order_by(ChittiMemberContribution.period_number)
            )
        ).scalars().all()
    )
    for contribution in contributions:
        contribution.expected_amount = Decimal("0")
        contribution.paid_amount = Decimal("0")
        contribution.remaining_amount = Decimal("0")
        contribution.status = "UPCOMING"
    first = contributions[0]
    first.expected_amount = Decimal("100")
    first.paid_amount = paid
    first.remaining_amount = max(Decimal("100") - paid, Decimal("0"))
    first.status = "PAID" if first.remaining_amount == 0 else "PARTIALLY_PAID"
    await db_session.flush()

    response = await client.get(
        f"/api/v1/chitti/{chitti['id']}/members/{members[0]['id']}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total_expected_amount"] == 100.0
    assert data["total_paid_amount"] == float(paid)
    assert data["outstanding_amount"] == expected_outstanding

    await db_session.refresh(first)
    assert first.paid_amount == paid


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

    reversal_headers = await _reversal_headers(db_session)
    insufficient_response = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{genuine_transaction_id}/reverse",
        json={"reversal_reason": "balance does not support reversal"},
        headers=reversal_headers,
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
        headers=reversal_headers,
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

    listed = await client.get(
        f"/api/v1/chitti/{chitti['id']}/payouts", headers=headers
    )
    assert listed.status_code == 200, listed.text
    payout_rows = listed.json()["data"]
    assert len(payout_rows) == 1
    assert payout_rows[0]["member_id"] == members[0]["id"]
    assert payout_rows[0]["customer_name"]
    assert payout_rows[0]["customer_name"] != chitti["name"]

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
        assert payouts[0].ledger_transaction_id == ledger[0].id

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

    # Free period 1 so the next batch can use a genuinely eligible period.
    async with fresh_sessions() as fresh:
        first_event = (await fresh.execute(
            select(ChittiLiftEvent).where(
                ChittiLiftEvent.chitti_id == UUID(chitti["id"]),
                ChittiLiftEvent.reversed_at.is_(None),
            )
        )).scalar_one()
        first_event_id = first_event.id

    async with sessions() as session:
        await ChittiService(session).reverse_lift(
            UUID(chitti["id"]), first_event_id,
            reason="test setup for peer slots",
            reversed_by=test_user["user"].id,
        )
        await session.commit()

    # Multi-slot rule: each membership slot lifts independently, so two
    # different members may record the same period in the same Chitti.
    different_members = await asyncio.gather(
        lift(members[0]["id"], 1),
        lift(members[1]["id"], 1),
    )
    assert all(isinstance(value, dict) for value in different_members), different_members

    async with fresh_sessions() as fresh:
        active = list((await fresh.execute(
            select(ChittiLiftEvent).where(
                ChittiLiftEvent.chitti_id == UUID(chitti["id"]),
                ChittiLiftEvent.reversed_at.is_(None),
            )
        )).scalars().all())
        assert len(active) == 2
        assert len({event.member_id for event in active}) == 2


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

        analytics = (
            await client.get("/api/v1/analytics/chitti/overview", headers=headers)
        ).json()["data"]
        member_metric = next(
            row for row in analytics["member_rows"]
            if row["member_id"] == members[0]["id"]
        )
        assert member_metric["expected_total"] == 23600.0
        assert member_metric["paid_total"] == 5000.0
        assert member_metric["pending_total"] == 18600.0

        chitti_metric = next(
            row for row in analytics["chitti_metrics"]
            if row["id"] == chitti["id"]
        )
        assert chitti_metric["expected"] == 23600.0
        assert chitti_metric["collected"] == 5000.0
        assert chitti_metric["pending"] == 18600.0


@pytest.mark.asyncio
async def test_lift_effective_values_override_stale_period_and_report_aggregates(
    client, test_user, db_session
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
            "idempotency_key": "lift-effective-report-reconciliation",
        },
        headers=headers,
    )
    assert contribution.status_code == 200, contribution.text
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

    chitti_row = (
        await db_session.execute(select(Chitti).where(Chitti.id == UUID(chitti["id"])))
    ).scalar_one()
    schedules = list((await db_session.execute(
        select(ChittiPeriodSchedule)
        .where(ChittiPeriodSchedule.chitti_id == chitti_row.id)
        .order_by(ChittiPeriodSchedule.period_number)
    )).scalars().all())
    contributions = list((await db_session.execute(
        select(ChittiMemberContribution)
        .where(ChittiMemberContribution.chitti_id == chitti_row.id)
        .order_by(ChittiMemberContribution.period_number)
    )).scalars().all())
    payment = (
        await db_session.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.chitti_id == chitti_row.id,
                ChittiTransaction.member_id == UUID(members[0]["id"]),
                ChittiTransaction.transaction_type == "CONTRIBUTION",
                ChittiTransaction.period_number == 1,
            )
        )
    ).scalar_one()
    payment.payment_date = schedules[1].due_date

    for schedule in schedules:
        schedule.expected_collection = Decimal("5000")
        schedule.actual_collection = (
            Decimal("5000") if schedule.period_number == 1 else Decimal("0")
        )
        schedule.pending_collection = (
            Decimal("0") if schedule.period_number == 1 else Decimal("5000")
        )
    # Simulate the legacy stale cache that used to exclude this still-due member
    # from report drill-downs even though the Lift-effective amount is positive.
    contributions[1].remaining_amount = Decimal("0")
    contributions[1].status = "PAID"
    await db_session.commit()

    first_date = schedules[0].due_date.isoformat()
    last_date = schedules[-1].due_date.isoformat()
    analytics_response = await client.get(
        "/api/v1/analytics/chitti/overview",
        params={"start_date": first_date, "end_date": last_date},
        headers=headers,
    )
    assert analytics_response.status_code == 200, analytics_response.text
    analytics = analytics_response.json()["data"]
    assert analytics["kpis"]["range_expected"] == 23600.0
    assert analytics["kpis"]["range_pending"] == 18600.0
    assert analytics["kpis"]["total_expected"] == 23600.0
    assert analytics["kpis"]["total_pending"] == 18600.0
    assert sum(row["expected"] for row in analytics["daily"]["series"]) == 23600.0
    assert analytics["daily"]["pending"] == 18600.0
    period_two_series = next(
        row for row in analytics["daily"]["series"]
        if row["date"] == schedules[1].due_date.isoformat()
    )
    assert period_two_series["collected"] == 5000.0
    assert period_two_series["pending"] == 6200.0
    metric = next(
        row for row in analytics["chitti_metrics"] if row["id"] == chitti["id"]
    )
    assert metric["expected"] == 23600.0
    assert metric["pending"] == 18600.0

    period_two_date = schedules[1].due_date.isoformat()
    report_response = await client.get(
        "/api/v1/reports/daily",
        params={"date": period_two_date},
        headers=headers,
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()["data"]
    assert report["chitti_expected"] == 6200.0
    assert report["chitti_collected"] == 5000.0
    assert report["chitti_pending"] == 6200.0
    pending = next(
        row for row in report["pending_details"]
        if row["source"] == "CHITTI"
        and row["reference_id"] == str(contributions[1].id)
    )
    assert pending["expected"] == 6200.0
    assert pending["pending"] == 6200.0
    assert pending["status"] != "PAID"

    plan_response = await client.get(
        f"/api/v1/reports/chitti-plans/{chitti_row.plan_id}/metrics",
        headers=headers,
    )
    assert plan_response.status_code == 200, plan_response.text
    plan_metrics = plan_response.json()["data"]
    assert Decimal(plan_metrics["total_expected"]) == Decimal("23600")
    assert Decimal(plan_metrics["total_collected"]) == Decimal("5000")
    assert Decimal(plan_metrics["total_pending"]) == Decimal("18600")


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
    account, _ = await create_finance_account(
        client,
        headers,
        customer,
        frequency="WEEKLY",
        number_of_installments=3,
    )
    account_id = account["id"]

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
