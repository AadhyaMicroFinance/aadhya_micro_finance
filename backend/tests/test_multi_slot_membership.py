from datetime import date
from uuid import UUID

import pytest

from app.core.exceptions import BadRequestException, ConflictException
from app.repositories.chitti_repo import ChittiContributionRepository
from app.services.chitti_service import ChittiService
from app.services.customer_service import CustomerService


@pytest.mark.asyncio
async def test_multi_slot_enrollment(db_session, test_user, test_customer):
    """One customer can own several independent, aliased slots in one Chitti."""
    svc = ChittiService(db_session)
    plan = await svc.create_plan(data={
        "name": "Multi Slot Plan",
        "chitti_type": "FIXED",
        "total_value": 15000,
        "currency": "INR",
        "member_count": 3,
        "frequency": "MONTHLY",
        "duration": 3,
        "contribution_rules": {"type": "FIXED", "installment_amount": 5000},
        "payout_rules": {"type": "SCHEDULED"},
        "start_date": date(2026, 1, 1),
    }, created_by=test_user["user"].id)
    chitti = await svc.create_chitti(data={
        "plan_id": str(plan["id"]),
        "name": "Multi Slot Chitti",
        "start_date": date(2026, 1, 1),
    }, created_by=test_user["user"].id)
    chitti_id = chitti["id"]
    customer_id = str(test_customer.id)

    first = await svc.add_member(
        chitti_id, customer_id=customer_id, member_number=1, payout_order=1
    )

    # A second slot for the same customer must be explicitly identifiable.
    with pytest.raises(BadRequestException) as missing_alias:
        await svc.add_member(
            chitti_id, customer_id=customer_id, member_number=2, payout_order=2
        )
    assert missing_alias.value.error_code == "ALIAS_REQUIRED"

    second = await svc.add_member(
        chitti_id,
        customer_id=customer_id,
        member_number=2,
        payout_order=2,
        alias="Archana Family",
    )
    third = await svc.add_member(
        chitti_id,
        customer_id=customer_id,
        member_number=3,
        payout_order=3,
        alias="Archana Business",
    )

    with pytest.raises(ConflictException) as duplicate_alias:
        await svc.add_member(
            chitti_id,
            customer_id=customer_id,
            member_number=4,
            payout_order=4,
            alias="Archana Family",
        )
    assert duplicate_alias.value.error_code == "DUPLICATE_ALIAS"

    # Case variants are the same slot identity, even at capacity: the alias
    # check runs before the capacity check.
    with pytest.raises(ConflictException) as case_alias:
        await svc.add_member(
            chitti_id,
            customer_id=customer_id,
            member_number=4,
            payout_order=4,
            alias="ARCHANA family",
        )
    assert case_alias.value.error_code == "DUPLICATE_ALIAS"

    # Capacity is counted per membership row, not per distinct customer.
    with pytest.raises(BadRequestException) as full:
        await svc.add_member(
            chitti_id,
            customer_id=customer_id,
            member_number=4,
            payout_order=4,
            alias="Fourth slot",
        )
    assert full.value.error_code == "CHITTI_FULL"

    members = await svc.list_members(chitti_id)
    assert {m["customer_id"] for m in members} == {customer_id}
    assert len(members) == 3
    assert len({m["id"] for m in members}) == 3
    assert {m["member_number"] for m in members} == {1, 2, 3}
    assert {m["alias"] for m in members} == {
        None, "Archana Family", "Archana Business"
    }
    assert {first["id"], second["id"], third["id"]} == {m["id"] for m in members}

    # Both enrollment paths now use the agreement workflow: members start as
    # PENDING_AGREEMENT and their schedules are materialised on confirmation.
    from app.services.agreement_service import AgreementService

    agreement_svc = AgreementService(db_session)
    for member in (first, second, third):
        agreement = await agreement_svc.generate_agreement(UUID(member["id"]))
        await agreement_svc.print_agreement(UUID(agreement["id"]))
        await agreement_svc.confirm_agreement(UUID(agreement["id"]))

    # Every slot owns a separate contribution schedule.
    contribution_repo = ChittiContributionRepository(db_session)
    schedules = []
    for member in (first, second, third):
        rows = await contribution_repo.get_by_member_id(member["id"])
        assert rows
        assert all(str(row.member_id) == member["id"] for row in rows)
        schedules.append({row.id for row in rows})
    assert schedules[0].isdisjoint(schedules[1])
    assert schedules[1].isdisjoint(schedules[2])

    # All slots remain consolidated under the same customer profile.
    ledger = await CustomerService(db_session).get_customer_ledger(test_customer.id)
    profile_slots = [c for c in ledger["chittis"] if c["id"] == chitti_id]
    assert {c["member_id"] for c in profile_slots} == {m["id"] for m in members}
    assert all(c["member_number"] in {1, 2, 3} for c in profile_slots)
    assert all("agreement_status" in c and "lift_status" in c for c in profile_slots)
