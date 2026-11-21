"""Route-level ownership checks for member/agreement endpoints.

A URL may name a Chitti and a member that do not belong to each other. The
services below the API intentionally resolve the member by ID alone, so the API
must validate the pair before any agreement or cancellation work starts.
"""

from datetime import date

import pytest

PLAN = {
    "name": "Route Scope Plan",
    "chitti_type": "FIXED",
    "total_value": "3000.00",
    "member_count": 4,
    "frequency": "WEEKLY",
    "duration": 3,
    "contribution_rules": {"type": "FIXED", "installment_amount": "1000.00"},
    "payout_rules": {"type": "SCHEDULED"},
}


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _plan(client, headers):
    resp = await client.post("/api/v1/chitti/plans", json=PLAN, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _chitti(client, headers, plan_id, name):
    resp = await client.post(
        "/api/v1/chitti/",
        json={
            "plan_id": plan_id,
            "name": name,
            "start_date": date.today().isoformat(),
            "member_count": 4,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _customer(client, headers, index):
    resp = await client.post(
        "/api/v1/customers/",
        json={
            "full_name": f"Route Scope Member {index}",
            "mobile_number": f"9000004{index:03d}",
            "address": "Hyderabad, Telangana",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _enroll(client, headers, chitti_id, customer_id, alias):
    resp = await client.post(
        f"/api/v1/chitti/{chitti_id}/members",
        json={"customer_id": customer_id, "alias": alias},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _assert_not_found(response, context):
    assert response.status_code == 404, f"{context}: {response.text}"
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND", body
    # The scope check resolves the member first; a missing agreement would
    # produce a different resource name.
    assert "Member" in body["error"]["message"], body


@pytest.mark.asyncio
async def test_agreement_and_cancel_routes_reject_mismatched_chitti(client, test_user):
    headers = _auth(test_user)
    plan = await _plan(client, headers)
    chitti_a = await _chitti(client, headers, plan["id"], "Route Scope Chitti A")
    chitti_b = await _chitti(client, headers, plan["id"], "Route Scope Chitti B")

    customer = await _customer(client, headers, 1)
    member_a1 = await _enroll(client, headers, chitti_a["id"], customer["id"], "A one")
    member_a2 = await _enroll(client, headers, chitti_a["id"], customer["id"], "A two")
    member_b1 = await _enroll(client, headers, chitti_b["id"], customer["id"], "B one")

    # Generate: a Chitti B URL must not create an agreement on a Chitti A member.
    _assert_not_found(
        await client.post(
            f"/api/v1/chitti/{chitti_b['id']}/members/{member_a1['id']}/agreement/generate",
            headers=headers,
        ),
        "generate with mismatched chitti",
    )

    # Get: no agreement exists yet, but the scope failure must be reported first.
    _assert_not_found(
        await client.get(
            f"/api/v1/chitti/{chitti_b['id']}/members/{member_a1['id']}/agreement",
            headers=headers,
        ),
        "get with mismatched chitti",
    )

    # A correctly scoped generate still works.
    generated = await client.post(
        f"/api/v1/chitti/{chitti_a['id']}/members/{member_a1['id']}/agreement/generate",
        headers=headers,
    )
    assert generated.status_code == 200, generated.text

    for action in ("get", "print", "confirm"):
        if action == "get":
            response = await client.get(
                f"/api/v1/chitti/{chitti_b['id']}/members/{member_a1['id']}/agreement",
                headers=headers,
            )
        else:
            response = await client.post(
                f"/api/v1/chitti/{chitti_b['id']}/members/{member_a1['id']}/agreement/{action}",
                headers=headers,
            )
        _assert_not_found(response, f"{action} with mismatched chitti")

    # Cancel: use a still-pending slot in Chitti A so a missing scope check
    # would otherwise succeed and mutate that slot.
    _assert_not_found(
        await client.post(
            f"/api/v1/chitti/{chitti_b['id']}/members/{member_a2['id']}/cancel",
            json={"reason": "mismatched URL"},
            headers=headers,
        ),
        "cancel with mismatched chitti",
    )

    # The correctly scoped URLs remain usable.
    agreement = await client.get(
        f"/api/v1/chitti/{chitti_a['id']}/members/{member_a1['id']}/agreement",
        headers=headers,
    )
    assert agreement.status_code == 200, agreement.text
    assert agreement.json()["data"]["agreement_status"] == "GENERATED"

    members_a = (await client.get(
        f"/api/v1/chitti/{chitti_a['id']}/members", headers=headers
    )).json()["data"]
    assert {m["id"] for m in members_a} == {member_a1["id"], member_a2["id"]}
    assert next(m for m in members_a if m["id"] == member_a2["id"])["status"] == "PENDING_AGREEMENT"

    members_b = (await client.get(
        f"/api/v1/chitti/{chitti_b['id']}/members", headers=headers
    )).json()["data"]
    assert {m["id"] for m in members_b} == {member_b1["id"]}


@pytest.mark.asyncio
async def test_api_enrollment_rejects_case_variant_alias(client, test_user):
    headers = _auth(test_user)
    plan = await _plan(client, headers)
    chitti = await _chitti(client, headers, plan["id"], "Alias Scope Chitti")
    first_customer = await _customer(client, headers, 2)
    second_customer = await _customer(client, headers, 3)

    first = await _enroll(client, headers, chitti["id"], first_customer["id"], "Slot A")
    assert first["alias"] == "Slot A"

    duplicate = await client.post(
        f"/api/v1/chitti/{chitti['id']}/members",
        json={"customer_id": second_customer["id"], "alias": "slot a"},
        headers=headers,
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "DUPLICATE_ALIAS"

    members = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/members", headers=headers
    )).json()["data"]
    assert len(members) == 1
