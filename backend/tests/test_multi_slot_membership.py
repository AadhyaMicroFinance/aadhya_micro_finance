from datetime import date
import pytest
from app.services.chitti_service import ChittiService


@pytest.mark.asyncio
async def test_multi_slot_enrollment(db_session, test_user, test_customer):
    svc = ChittiService(db_session)
    plan = await svc.create_plan(data={
        "name": "Multi Slot Plan",
        "chitti_type": "FIXED",
        "total_value": 10000,
        "currency": "INR",
        "member_count": 2,
        "frequency": "MONTHLY",
        "duration": 2,
        "contribution_rules": {"type": "FIXED", "installment_amount": 5000},
        "payout_rules": {"type": "SCHEDULED"},
        "start_date": date(2026,1,1),
    }, created_by=test_user["user"].id)
    chitti = await svc.create_chitti(data={"plan_id": str(plan["id"]), "name": "Multi Slot Chitti", "start_date": date(2026,1,1)}, created_by=test_user["user"].id)
    cid = chitti["id"]
    await svc.add_member(cid, customer_id=str(test_customer.id), member_number=1, payout_order=1)
    await svc.add_member(cid, customer_id=str(test_customer.id), member_number=2, alias="Archana Family", payout_order=2)
    members = await svc.list_members(cid)
    assert len(members) == 2
    assert members[0]["alias"] is None
    assert members[1]["alias"] == "Archana Family"
