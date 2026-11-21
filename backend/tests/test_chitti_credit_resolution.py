"""Migration 0007: credit, excess, over-allocation and refund behaviour.

These tests cover the operator-driven flows only. Nothing here relies on
automatic credit movement, which revision 0007 removes.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.chitti import ChittiPaymentAllocation, ChittiTransaction

NEW_TRANSACTION_TYPES = ("CREDIT_UTILIZATION", "EXCESS_RESOLUTION", "REFUND")


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _customer(client, headers, index=1):
    response = await client.post(
        "/api/v1/customers/",
        json={
            "full_name": f"Credit Member {index}",
            "mobile_number": f"94400000{index:02d}",
            "address": "Hyderabad, Telangana",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _running_chitti(
    client,
    headers,
    *,
    total_value="200.00",
    duration=2,
    installment="100.00",
    rules=None,
    chitti_type="FIXED",
):
    contribution_rules = rules or {
        "type": "FIXED",
        "installment_amount": installment,
        "partial_payments_allowed": True,
    }
    plan = (
        await client.post(
            "/api/v1/chitti/plans",
            json={
                "name": f"Credit plan {uuid4().hex[:6]}",
                "chitti_type": chitti_type,
                "total_value": total_value,
                "member_count": 1,
                "frequency": "DAILY",
                "duration": duration,
                "contribution_rules": contribution_rules,
                "payout_rules": {
                    "type": "SCHEDULED",
                    "payout_order": "MEMBER_NUMBER",
                },
            },
            headers=headers,
        )
    ).json()["data"]
    chitti = (
        await client.post(
            "/api/v1/chitti/",
            json={
                "plan_id": plan["id"],
                "name": f"Credit chitti {uuid4().hex[:6]}",
                "member_count": 1,
                "start_date": date.today().isoformat(),
            },
            headers=headers,
        )
    ).json()["data"]
    customer = await _customer(client, headers)
    member = (
        await client.post(
            f"/api/v1/chitti/{chitti['id']}/members",
            json={"customer_id": customer["id"], "payout_order": 1},
            headers=headers,
        )
    ).json()["data"]
    for action in ("generate", "print", "confirm"):
        response = await client.post(
            f"/api/v1/chitti/{chitti['id']}/members/{member['id']}/agreement/{action}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
    started = await client.post(
        f"/api/v1/chitti/{chitti['id']}/start", headers=headers
    )
    assert started.status_code == 200, started.text
    return chitti["id"], member["id"], customer["id"]


async def _pay(client, headers, chitti_id, member_id, amount, key, period=1):
    response = await client.post(
        f"/api/v1/chitti/{chitti_id}/contributions",
        json={
            "member_id": member_id,
            "period_number": period,
            "amount": amount,
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": key,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _member(client, headers, chitti_id, member_id):
    rows = (
        await client.get(f"/api/v1/chitti/{chitti_id}/members", headers=headers)
    ).json()["data"]
    return next(row for row in rows if row["id"] == member_id)


@pytest.mark.asyncio
async def test_new_enum_labels_round_trip_through_orm(db_session, client, test_user):
    """Insert, commit, reload, filter and serialize every new ledger type."""
    headers = _auth(test_user)
    chitti_id, member_id, _ = await _running_chitti(client, headers)

    created = {}
    for index, transaction_type in enumerate(NEW_TRANSACTION_TYPES):
        row = ChittiTransaction(
            id=uuid4(),
            chitti_id=UUID(chitti_id),
            member_id=UUID(member_id),
            transaction_type=transaction_type,
            amount=Decimal("10.00"),
        )
        db_session.add(row)
        created[transaction_type] = row.id
    await db_session.commit()
    db_session.expire_all()

    for transaction_type, row_id in created.items():
        stored = await db_session.get(ChittiTransaction, row_id)
        assert stored.transaction_type == transaction_type
        assert isinstance(stored.transaction_type, str)

    for transaction_type in NEW_TRANSACTION_TYPES:
        found = (
            await db_session.execute(
                select(ChittiTransaction).where(
                    ChittiTransaction.transaction_type == transaction_type
                )
            )
        ).scalars().all()
        assert [row.transaction_type for row in found] == [transaction_type]

    combined = (
        await db_session.execute(
            select(ChittiTransaction.transaction_type)
            .where(ChittiTransaction.transaction_type.in_(NEW_TRANSACTION_TYPES))
            .order_by(ChittiTransaction.transaction_type)
            .distinct()
        )
    ).scalars().all()
    assert list(combined) == sorted(NEW_TRANSACTION_TYPES)

    # Allocation rows carry the new type/event labels too.
    allocation = ChittiPaymentAllocation(
        id=uuid4(),
        chitti_id=UUID(chitti_id),
        member_id=UUID(member_id),
        source_transaction_id=created["REFUND"],
        event_transaction_id=created["EXCESS_RESOLUTION"],
        contribution_id=None,
        allocation_type="UNRESOLVED",
        event_type="EXCESS_RESOLUTION",
        amount=Decimal("-5.00"),
    )
    db_session.add(allocation)
    await db_session.commit()
    await db_session.refresh(allocation)
    stored_allocation = allocation
    assert stored_allocation.allocation_type == "UNRESOLVED"
    assert stored_allocation.event_type == "EXCESS_RESOLUTION"

    assert (
        await db_session.execute(
            select(ChittiPaymentAllocation).where(
                ChittiPaymentAllocation.allocation_type == "UNRESOLVED"
            )
        )
    ).scalars().all()

    # API serialization surfaces the same enum values as plain strings.
    refunds = (
        await client.get(f"/api/v1/chitti/{chitti_id}/refunds", headers=headers)
    ).json()["data"]
    assert [row["amount"] for row in refunds] == [10.0]


@pytest.mark.asyncio
async def test_receipt_excess_becomes_credit_only_by_operator_action(
    client, test_user, db_session
):
    headers = _auth(test_user)
    chitti_id, member_id, customer_id = await _running_chitti(
        client,
        headers,
        total_value="120000.00",
        duration=4,
        chitti_type="LIFT_BASED",
        rules={"type": "LIFT_BASED", "regular_amount": "5000.00"},
    )

    receipt = await _pay(client, headers, chitti_id, member_id, "25000.00", "receipt-25000")
    assert receipt["allocated_amount"] == 20000.0
    assert receipt["unallocated_credit"] == 0.0
    assert receipt["unresolved_excess"] == 5000.0
    receipt_id = receipt["transaction_id"]

    position = (
        await client.get(f"/api/v1/chitti/customers/{customer_id}/credit", headers=headers)
    ).json()["data"]
    assert position["available_credit"] == 0.0
    assert position["unresolved_excess"] == 5000.0
    assert position["allocated"] == 20000.0

    resolved = await client.post(
        f"/api/v1/chitti/{chitti_id}/excess-resolutions",
        json={
            "member_id": member_id,
            "source_receipt_id": receipt_id,
            "amount": "30.00",
            "reason": "Operator converts part of the excess",
            "idempotency_key": "resolve-excess-30",
        },
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["data"]["unresolved_excess"] == 4970.0
    assert resolved.json()["data"]["available_credit"] == 30.0
    assert resolved.json()["data"]["audit_log_id"]

    # A lift raises the instalments, so a period is outstanding again. The
    # operator, not the lift, decides that the credit pays for it.
    lift = await client.post(
        f"/api/v1/chitti/{chitti_id}/lifts",
        json={
            "member_id": member_id,
            "period_number": 1,
            "lift_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert lift.status_code == 200, lift.text

    applied = await client.post(
        f"/api/v1/chitti/{chitti_id}/credit-applications",
        json={
            "member_id": member_id,
            "source_receipt_id": receipt_id,
            "target_period_number": 2,
            "amount": "30.00",
            "reason": "Apply credit to period 2",
            "idempotency_key": "apply-credit-30",
        },
        headers=headers,
    )
    assert applied.status_code == 200, applied.text
    applied_data = applied.json()["data"]

    member = await _member(client, headers, chitti_id, member_id)
    assert member["unallocated_credit"] == 0
    assert member["unresolved_excess"] == 4970
    assert member["total_paid"] == 20030

    replay = await client.post(
        f"/api/v1/chitti/{chitti_id}/credit-applications",
        json={
            "member_id": member_id,
            "source_receipt_id": receipt_id,
            "target_period_number": 2,
            "amount": "30.00",
            "reason": "Apply credit to period 2",
            "idempotency_key": "apply-credit-30",
        },
        headers=headers,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["duplicate"] is True
    assert replay.json()["data"]["transaction_id"] == applied_data["transaction_id"]
    assert replay.json()["data"]["audit_log_id"] == applied_data["audit_log_id"]

    usage = (
        await db_session.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.transaction_type == "CREDIT_UTILIZATION"
            )
        )
    ).scalars().all()
    assert len(usage) == 1


@pytest.mark.asyncio
async def test_refund_ceilings_replay_and_receipt_reversal(
    client, test_user, db_session
):
    headers = _auth(test_user)
    chitti_id, member_id, _ = await _running_chitti(client, headers, duration=2)
    receipt = await _pay(client, headers, chitti_id, member_id, "300.00", "receipt-300")
    receipt_id = receipt["transaction_id"]
    assert receipt["unresolved_excess"] == 100.0

    resolved = await client.post(
        f"/api/v1/chitti/{chitti_id}/excess-resolutions",
        json={
            "member_id": member_id,
            "source_receipt_id": receipt_id,
            "amount": "100.00",
            "reason": "Convert all excess",
            "idempotency_key": "resolve-all-excess",
        },
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text

    first = await client.post(
        f"/api/v1/chitti/{chitti_id}/refunds",
        json={
            "source_receipt_id": receipt_id,
            "source_bucket": "CREDIT",
            "source_member_id": member_id,
            "amount": "40.00",
            "refund_method": "CASH",
            "reason": "Customer asked for part of the credit",
            "idempotency_key": "refund-40",
        },
        headers=headers,
    )
    assert first.status_code == 200, first.text
    first_data = first.json()["data"]
    assert first_data["cumulative_refunded"] == 40.0
    assert first_data["remaining_refundable"] == 260.0

    duplicate = await client.post(
        f"/api/v1/chitti/{chitti_id}/refunds",
        json={
            "source_receipt_id": receipt_id,
            "source_bucket": "CREDIT",
            "source_member_id": member_id,
            "amount": "40.00",
            "refund_method": "CASH",
            "reason": "Customer asked for part of the credit",
            "idempotency_key": "refund-40",
        },
        headers=headers,
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["data"]["duplicate"] is True
    assert duplicate.json()["data"]["transaction_id"] == first_data["transaction_id"]
    assert duplicate.json()["data"]["audit_log_id"] == first_data["audit_log_id"]

    second = await client.post(
        f"/api/v1/chitti/{chitti_id}/refunds",
        json={
            "source_receipt_id": receipt_id,
            "source_bucket": "CREDIT",
            "source_member_id": member_id,
            "amount": "60.00",
            "refund_method": "UPI",
            "reference_number": "UPI-REFUND-1",
            "reason": "Refund the remaining credit",
            "idempotency_key": "refund-60",
        },
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["cumulative_refunded"] == 100.0

    over = await client.post(
        f"/api/v1/chitti/{chitti_id}/refunds",
        json={
            "source_receipt_id": receipt_id,
            "source_bucket": "CREDIT",
            "source_member_id": member_id,
            "amount": "1.00",
            "refund_method": "CASH",
            "reason": "One rupee too many",
            "idempotency_key": "refund-too-much",
        },
        headers=headers,
    )
    assert over.status_code == 400
    assert over.json()["error"]["code"] == "NO_ELIGIBLE_BALANCE"

    refunds = (
        await client.get(
            f"/api/v1/chitti/{chitti_id}/refunds",
            params={"receipt_id": receipt_id},
            headers=headers,
        )
    ).json()["data"]
    assert sum(row["amount"] for row in refunds) == 100.0

    reversal = await client.post(
        f"/api/v1/chitti/{chitti_id}/transactions/{receipt_id}/reverse",
        json={"reversal_reason": "Receipt reversed after refunds"},
        headers=await _super_admin_headers(db_session),
    )
    assert reversal.status_code == 200, reversal.text
    assert reversal.json()["data"]["amount"] == 200.0

    after = await client.post(
        f"/api/v1/chitti/{chitti_id}/refunds",
        json={
            "source_receipt_id": receipt_id,
            "source_bucket": "CREDIT",
            "source_member_id": member_id,
            "amount": "1.00",
            "refund_method": "CASH",
            "reason": "Refund after reversal",
            "idempotency_key": "refund-after-reversal",
        },
        headers=headers,
    )
    assert after.status_code == 400
    assert after.json()["error"]["code"] in {"REVERSED_RECEIPT", "NO_ELIGIBLE_BALANCE"}

    refund_rows = (
        await db_session.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.transaction_type == "REFUND"
            )
        )
    ).scalars().all()
    assert len(refund_rows) == 2


@pytest.mark.asyncio
async def test_cash_received_excludes_reversed_receipt(client, db_session, test_user):
    headers = _auth(test_user)
    chitti_id, member_id, customer_id = await _running_chitti(
        client, headers, total_value="100.00", duration=1, installment="100.00"
    )
    receipt = await _pay(
        client, headers, chitti_id, member_id, "100.00", "cash-before-reversal"
    )

    before = (
        await client.get(
            f"/api/v1/chitti/customers/{customer_id}/credit", headers=headers
        )
    ).json()["data"]
    assert before["cash_received"] == 100.0

    reversal = await client.post(
        f"/api/v1/chitti/{chitti_id}/transactions/{receipt['transaction_id']}/reverse",
        json={"reversal_reason": "Customer paid twice"},
        headers=await _super_admin_headers(db_session),
    )
    assert reversal.status_code == 200, reversal.text

    after = (
        await client.get(
            f"/api/v1/chitti/customers/{customer_id}/credit", headers=headers
        )
    ).json()["data"]
    assert after["cash_received"] == 0.0


async def _super_admin_headers(db_session) -> dict:
    """Refunds are reversible; receipt reversal still needs payments:reverse."""
    from app.core.security import create_access_token
    from app.models.user import User

    user = User(
        id=uuid4(),
        username=f"supervisor-{uuid4().hex[:6]}",
        email=f"supervisor-{uuid4().hex[:6]}@test.com",
        password_hash="x",
        full_name="Supervisor",
        role="SUPER_ADMIN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_overallocation_after_lift_reversal_is_operator_resolved(
    client, test_user, db_session
):
    headers = _auth(test_user)
    plan = (
        await client.post(
            "/api/v1/chitti/plans",
            json={
                "name": "P0.7 over-allocation plan",
                "chitti_type": "LIFT_BASED",
                "total_value": "120000.00",
                "member_count": 1,
                "frequency": "DAILY",
                "duration": 4,
                "contribution_rules": {
                    "type": "LIFT_BASED",
                    "regular_amount": "5000.00",
                },
                "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
            },
            headers=headers,
        )
    ).json()["data"]
    chitti = (
        await client.post(
            "/api/v1/chitti/",
            json={
                "plan_id": plan["id"],
                "name": "P0.7 over-allocation chitti",
                "member_count": 1,
                "start_date": date.today().isoformat(),
            },
            headers=headers,
        )
    ).json()["data"]
    customer = await _customer(client, headers, index=9)
    member = (
        await client.post(
            f"/api/v1/chitti/{chitti['id']}/members",
            json={"customer_id": customer["id"], "payout_order": 1},
            headers=headers,
        )
    ).json()["data"]
    for action in ("generate", "print", "confirm"):
        response = await client.post(
            f"/api/v1/chitti/{chitti['id']}/members/{member['id']}/agreement/{action}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
    started = await client.post(
        f"/api/v1/chitti/{chitti['id']}/start", headers=headers
    )
    assert started.status_code == 200, started.text

    lift = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts",
        json={
            "member_id": member["id"],
            "period_number": 1,
            "lift_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert lift.status_code == 200, lift.text

    receipt = await _pay(
        client, headers, chitti["id"], member["id"], "23600.00", "receipt-lift-total"
    )
    receipt_id = receipt["transaction_id"]
    assert receipt["unresolved_excess"] == 0.0

    reversed_lift = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts/{lift.json()['data']['id']}/reverse",
        json={"reversal_reason": "Lift was recorded in error"},
        headers=headers,
    )
    assert reversed_lift.status_code == 200, reversed_lift.text

    over = (
        await client.get(
            f"/api/v1/chitti/{chitti['id']}/members/{member['id']}/overallocations",
            headers=headers,
        )
    ).json()["data"]
    assert over["total_overallocated"] == 3600.0
    target = next(row for row in over["overallocations"] if row["period_number"] == 2)
    assert target["overallocated_amount"] == 1200.0
    assert target["funding"][0]["receipt_id"] == receipt_id

    resolved = await client.post(
        f"/api/v1/chitti/{chitti['id']}/overallocation-resolutions",
        json={
            "member_id": member["id"],
            "source_period_number": 2,
            "source_receipt_id": receipt_id,
            "mode": "TO_CREDIT",
            "amount": "1200.00",
            "reason": "Return the surplus to member credit",
            "idempotency_key": "overallocation-to-credit",
        },
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text

    member_data = await _member(client, headers, chitti["id"], member["id"])
    assert member_data["unallocated_credit"] == 1200
    assert member_data["total_paid"] == 22400

    remaining = (
        await client.get(
            f"/api/v1/chitti/{chitti['id']}/members/{member['id']}/overallocations",
            headers=headers,
        )
    ).json()["data"]
    assert remaining["total_overallocated"] == 2400.0
