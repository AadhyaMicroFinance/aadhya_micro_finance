"""Concurrent agreement generation must create exactly one document per slot."""

import asyncio
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import BadRequestException, ConflictException
from app.models.chitti import ChittiAgreement
from app.services.agreement_service import AgreementService


PLAN = {
    "name": "Concurrent Agreement Plan",
    "chitti_type": "FIXED",
    "total_value": "2000.00",
    "member_count": 2,
    "frequency": "DAILY",
    "duration": 2,
    "contribution_rules": {"type": "FIXED", "installment_amount": "1000.00"},
    "payout_rules": {"type": "SCHEDULED"},
}


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


@pytest.mark.asyncio
async def test_concurrent_generate_creates_only_one_agreement(
    client, test_user, test_engine, db_session
):
    headers = _auth(test_user)
    plan = (await client.post("/api/v1/chitti/plans", json=PLAN, headers=headers)).json()["data"]
    chitti = (await client.post(
        "/api/v1/chitti/",
        json={
            "plan_id": plan["id"],
            "name": "Concurrent Agreement Chitti",
            "start_date": date.today().isoformat(),
            "member_count": 2,
        },
        headers=headers,
    )).json()["data"]
    customer = (await client.post(
        "/api/v1/customers/",
        json={
            "full_name": "Concurrent Agreement Member",
            "mobile_number": "9000007001",
            "address": "Hyderabad, Telangana",
        },
        headers=headers,
    )).json()["data"]
    member = (await client.post(
        f"/api/v1/chitti/{chitti['id']}/members",
        json={"customer_id": customer["id"]},
        headers=headers,
    )).json()["data"]
    assert member["status"] == "PENDING_AGREEMENT"
    await db_session.commit()

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    member_id = UUID(member["id"])

    async def generate():
        async with sessions() as session:
            try:
                agreement = await AgreementService(session).generate_agreement(member_id)
                return ("ok", agreement["id"])
            except Exception as exc:  # noqa: BLE001 - concurrent loser is asserted below
                return ("error", exc)

    first, second = await asyncio.gather(generate(), generate())
    outcomes = [first, second]
    winners = [value for status, value in outcomes if status == "ok"]
    losers = [value for status, value in outcomes if status == "error"]

    assert len(winners) == 1, outcomes
    assert len(losers) == 1, outcomes
    assert isinstance(losers[0], (BadRequestException, ConflictException))
    assert getattr(losers[0], "error_code", None) in {
        "DUPLICATE_AGREEMENT", "BadRequestException", "BAD_REQUEST",
    }

    async with sessions() as session:
        agreements = (await session.execute(
            select(ChittiAgreement).where(ChittiAgreement.chitti_member_id == member_id)
        )).scalars().all()
        assert len(agreements) == 1
        assert str(agreements[0].id) == winners[0]
