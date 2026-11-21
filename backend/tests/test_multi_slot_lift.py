"""Per-membership lift events in a multi-slot Chitti."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictException
from app.models.chitti import ChittiLiftEvent
from app.repositories.chitti_repo import ChittiContributionRepository
from app.services.chitti_service import ChittiService


PLAN = {
    "name": "Multi Slot Lift Plan",
    "chitti_type": "LIFT_BASED",
    "total_value": "120000.00",
    "member_count": 2,
    "frequency": "DAILY",
    "duration": 4,
    "contribution_rules": {"type": "LIFT_BASED", "regular_amount": "5000.00"},
    "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
}


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _activate(client, headers, chitti_id, member_id):
    for action in ("generate", "print", "confirm"):
        response = await client.post(
            f"/api/v1/chitti/{chitti_id}/members/{member_id}/agreement/{action}",
            headers=headers,
        )
        assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_two_slots_of_same_customer_lift_same_period_independently(
    client, test_user, db_session
):
    headers = _auth(test_user)
    plan = (await client.post("/api/v1/chitti/plans", json=PLAN, headers=headers)).json()["data"]
    chitti = (await client.post(
        "/api/v1/chitti/",
        json={
            "plan_id": plan["id"],
            "name": "Multi Slot Lift Chitti",
            "member_count": 2,
            "start_date": date.today().isoformat(),
        },
        headers=headers,
    )).json()["data"]
    chitti_id = chitti["id"]

    customer = (await client.post(
        "/api/v1/customers/",
        json={
            "full_name": "Repeat Lift Customer",
            "mobile_number": "9000006001",
            "address": "Hyderabad, Telangana",
        },
        headers=headers,
    )).json()["data"]

    slots = []
    for alias in ("Lift slot one", "Lift slot two"):
        member = (await client.post(
            f"/api/v1/chitti/{chitti_id}/members",
            json={"customer_id": customer["id"], "alias": alias},
            headers=headers,
        )).json()["data"]
        await _activate(client, headers, chitti_id, member["id"])
        slots.append(member)

    assert len({slot["id"] for slot in slots}) == 2
    assert len({slot["member_number"] for slot in slots}) == 2

    started = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert started.status_code == 200, started.text

    svc = ChittiService(db_session)
    first = await svc.record_lift(
        UUID(chitti_id), member_id=slots[0]["id"], period_number=1,
        lift_date=date.today(), recorded_by=test_user["user"].id,
    )
    second = await svc.record_lift(
        UUID(chitti_id), member_id=slots[1]["id"], period_number=1,
        lift_date=date.today(), recorded_by=test_user["user"].id,
    )
    assert first["member_id"] == slots[0]["id"]
    assert second["member_id"] == slots[1]["id"]
    assert first["period_number"] == second["period_number"] == 1

    with pytest.raises(ConflictException) as duplicate:
        await svc.record_lift(
            UUID(chitti_id), member_id=slots[0]["id"], period_number=1,
            lift_date=date.today(), recorded_by=test_user["user"].id,
        )
    assert duplicate.value.error_code == "DUPLICATE_LIFT_PERIOD"

    events = (await db_session.execute(
        select(ChittiLiftEvent).where(
            ChittiLiftEvent.chitti_id == UUID(chitti_id),
            ChittiLiftEvent.reversed_at.is_(None),
        )
    )).scalars().all()
    assert len(events) == 2
    assert {event.member_id for event in events} == {UUID(slot["id"]) for slot in slots}
    assert {event.period_number for event in events} == {1}

    # The approved 1% surcharge formula is still per member, per lift period.
    contribution_repo = ChittiContributionRepository(db_session)
    for slot in slots:
        rows = await contribution_repo.get_by_member_id(UUID(slot["id"]))
        period_two = next(row for row in rows if row.period_number == 2)
        assert period_two.expected_amount == Decimal("6200.00")
