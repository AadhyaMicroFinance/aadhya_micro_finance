"""
End-to-end Chitti regression tests.

Covers the reported defects:
  BUG-001  enrolled member count must be identical on dashboard, summary and
           the members list
  BUG-002  duplicate enrollment in the SAME chitti is rejected with a
           structured DUPLICATE_ENROLLMENT error, while the same customer may
           join a DIFFERENT chitti
  BUG-003  activation prerequisites are reported with exact reasons instead of
           an opaque failure
  BUG-004  a successful start persists RUNNING in the database and is visible
           on re-read
  IMP-001  no NaN/Infinity reaches the JSON payload

These tests run against an isolated test database (see conftest.TEST_DATABASE_URL)
and never touch development or production data.
"""

import math
from datetime import date

import pytest

PLAN = {
    "name": "Regression Weekly Chitti",
    "chitti_type": "FIXED",
    "total_value": "10000.00",
    "member_count": 10,
    "frequency": "WEEKLY",
    "duration": 10,
    "contribution_rules": {"type": "FIXED", "installment_amount": "1000.00"},
    "payout_rules": {"type": "SCHEDULED"},
}


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _make_plan(client, headers):
    resp = await client.post("/api/v1/chitti/plans", json=PLAN, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _make_chitti(client, headers, plan_id, name="Regression Chitti"):
    resp = await client.post(
        "/api/v1/chitti/",
        json={
            "plan_id": plan_id,
            "name": name,
            "start_date": date.today().isoformat(),
            "member_count": 10,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _make_customers(client, headers, count):
    customers = []
    for i in range(count):
        resp = await client.post(
            "/api/v1/customers/",
            json={
                "full_name": f"Regression Member {i + 1}",
                "mobile_number": f"90000000{i:02d}",
                "address": "Hyderabad, Telangana",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        customers.append(resp.json()["data"])
    return customers


async def _enroll(client, headers, chitti_id, customer_id, payout_order):
    resp = await client.post(
        f"/api/v1/chitti/{chitti_id}/members",
        json={"customer_id": customer_id, "payout_order": payout_order},
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
    return resp.json()["data"]


def _assert_finite(payload):
    """Walk a JSON payload and fail on NaN/Infinity anywhere."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            _assert_finite(value) if isinstance(value, (dict, list)) else None
            if isinstance(value, float) and not math.isfinite(value):
                raise AssertionError(f"non-finite number in field {key}: {value}")
    elif isinstance(payload, list):
        for item in payload:
            _assert_finite(item)


@pytest.mark.asyncio
async def test_member_count_duplicate_and_activation(client, test_user):
    headers = _auth(test_user)
    plan = await _make_plan(client, headers)
    chitti = await _make_chitti(client, headers, plan["id"])
    chitti_id = chitti["id"]

    # ---- Enroll 10 members -------------------------------------------------
    customers = await _make_customers(client, headers, 10)
    members = []
    for index, customer in enumerate(customers, start=1):
        members.append(await _enroll(client, headers, chitti_id, customer["id"], index))

    # BUG-001: dashboard, summary and members list must agree.
    dashboard = (await client.get("/api/v1/chitti/dashboard", headers=headers)).json()["data"]
    item = next(i for i in dashboard if i["id"] == chitti_id)
    assert item["member_count"] == 10
    assert item["enrolled_members"] == 10
    assert item["member_capacity"] == 10
    assert item["active_members"] == 0, "no agreement has been confirmed yet"

    members_resp = await client.get(f"/api/v1/chitti/{chitti_id}/members", headers=headers)
    assert len(members_resp.json()["data"]) == 10

    summary = (await client.get(f"/api/v1/chitti/{chitti_id}/summary", headers=headers)).json()["data"]
    assert summary["enrolled_members"] == 10
    assert summary["member_count"] == summary["member_capacity"] == 10
    assert summary["active_members"] == 0

    # BUG-002: duplicate enrollment in the same chitti.
    duplicate = await client.post(
        f"/api/v1/chitti/{chitti_id}/members",
        json={"customer_id": customers[0]["id"]},
        headers=headers,
    )
    assert duplicate.status_code == 409, duplicate.text
    error = duplicate.json()["error"]
    assert error["code"] == "DUPLICATE_ENROLLMENT"
    assert error["message"] == "This member is already enrolled in this Chitti."
    assert error["details"]["existing_member_id"] == members[0]["id"]
    after_duplicate = (await client.get(f"/api/v1/chitti/{chitti_id}/members", headers=headers)).json()["data"]
    assert len(after_duplicate) == 10, "a rejected duplicate must not create a row"

    # Re-enrolment after cancellation reuses the existing row instead of
    # violating uq_chitti_member_customer (which used to surface as HTTP 500).
    cancelled = await client.post(
        f"/api/v1/chitti/{chitti_id}/members/{members[1]['id']}/cancel",
        json={"reason": "regression test"},
        headers=headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    re_added = await _enroll(client, headers, chitti_id, customers[1]["id"], 11)
    assert re_added["id"] == members[1]["id"]
    assert re_added["status"] == "PENDING_AGREEMENT"

    # The list endpoint used by "All Chittis" exposes the same counts.
    listed = (await client.get("/api/v1/chitti/", headers=headers)).json()["data"]
    listed_item = next(c for c in listed if c["id"] == chitti_id)
    assert listed_item["enrolled_members"] == 10
    assert listed_item["member_capacity"] == 10

    # BUG-002: the same customer may join a DIFFERENT chitti.
    other_chitti = await _make_chitti(client, headers, plan["id"], name="Regression Chitti 2")
    other_member = await _enroll(client, headers, other_chitti["id"], customers[0]["id"], 1)
    assert other_member["customer_id"] == customers[0]["id"]

    # Capacity is enforced against enrolled members, not ACTIVE only.
    # customers[0] is already enrolled in other_chitti, so fill the rest.
    for index, customer in enumerate(customers[1:], start=2):
        await _enroll(client, headers, other_chitti["id"], customer["id"], index)

    extra = (
        await client.post(
            "/api/v1/customers/",
            json={"full_name": "Capacity Probe", "mobile_number": "9111111111"},
            headers=headers,
        )
    ).json()["data"]
    full = await client.post(
        f"/api/v1/chitti/{other_chitti['id']}/members",
        json={"customer_id": extra["id"]},
        headers=headers,
    )
    assert full.status_code == 400, full.text
    assert full.json()["error"]["code"] == "CHITTI_FULL"
    assert full.json()["error"]["details"]["available_slots"] == 0

    # ---- BUG-003: blocked activation explains itself -----------------------
    activation = (await client.get(f"/api/v1/chitti/{chitti_id}/activation", headers=headers)).json()["data"]
    assert activation["can_activate"] is False
    assert activation["display_state"] == "ACTIVATION_BLOCKED"
    codes = {b["code"] for b in activation["blockers"]}
    assert "NO_ACTIVE_MEMBERS" in codes

    blocked = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert blocked.status_code == 400, blocked.text
    blocked_error = blocked.json()["error"]
    assert blocked_error["code"] == "ACTIVATION_BLOCKED"
    assert blocked_error["details"]["blockers"], "blockers must be machine-readable"
    assert any("agreement" in b["message"].lower() for b in blocked_error["details"]["blockers"])

    # BUG-004: nothing was persisted while activation is blocked.
    unchanged = (await client.get(f"/api/v1/chitti/{chitti_id}", headers=headers)).json()["data"]
    assert unchanged["status"] == "DRAFT"

    # ---- Activate one member through the agreement workflow ---------------
    await _activate_member(client, headers, chitti_id, members[0]["id"])
    members_after = (await client.get(f"/api/v1/chitti/{chitti_id}/members", headers=headers)).json()["data"]
    activated = next(m for m in members_after if m["id"] == members[0]["id"])
    assert activated["status"] == "ACTIVE"

    activation_ready = (await client.get(f"/api/v1/chitti/{chitti_id}/activation", headers=headers)).json()["data"]
    assert activation_ready["can_activate"] is True
    assert activation_ready["active_members"] == 1
    assert activation_ready["pending_agreements"] == 9
    assert {w["code"] for w in activation_ready["warnings"]} == {"PARTIAL_AGREEMENTS"}

    # ---- BUG-004: start persists and is visible on re-read ---------------
    started = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["data"]["status"] == "RUNNING"

    persisted = (await client.get(f"/api/v1/chitti/{chitti_id}", headers=headers)).json()["data"]
    assert persisted["status"] == "RUNNING"

    dashboard_after = (await client.get("/api/v1/chitti/dashboard", headers=headers)).json()["data"]
    item_after = next(i for i in dashboard_after if i["id"] == chitti_id)
    assert item_after["status"] == "RUNNING"
    assert item_after["member_count"] == 10

    summary_after = (await client.get(f"/api/v1/chitti/{chitti_id}/summary", headers=headers)).json()["data"]
    assert summary_after["display_state"] == "ACTIVE"
    assert summary_after["activation"]["can_activate"] is False
    assert summary_after["financials_source"] == "contributions"
    # One ACTIVE member => 10 weekly installments of 1000.
    assert summary_after["expected_collection"] == 10000.0
    assert summary_after["actual_collection"] == 0.0
    assert summary_after["pending_collection"] == 10000.0

    # IMP-001: every numeric value in the payload is finite.
    _assert_finite(summary_after)
    _assert_finite(item_after)

    # Pause/resume still works: resuming is not a "start", so the
    # only-DRAFT-can-start rule must not block it.
    paused = await client.post(f"/api/v1/chitti/{chitti_id}/pause", headers=headers)
    assert paused.status_code == 200, paused.text
    assert paused.json()["data"]["status"] == "PAUSED"
    resumed = await client.post(f"/api/v1/chitti/{chitti_id}/resume", headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["data"]["status"] == "RUNNING"

    # Starting twice is rejected (Start must disappear once RUNNING).
    again = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert again.status_code == 400
    assert again.json()["error"]["code"] in ("ACTIVATION_BLOCKED", "INVALID_STATUS_TRANSITION")


@pytest.mark.asyncio
async def test_analytics_reports_enrolled_members(client, test_user):
    """Analytics must use the same enrolled-member definition as the dashboard."""
    headers = _auth(test_user)
    plan = await _make_plan(client, headers)
    chitti = await _make_chitti(client, headers, plan["id"], name="Analytics Chitti")
    customers = await _make_customers(client, headers, 3)
    for index, customer in enumerate(customers, start=1):
        await _enroll(client, headers, chitti["id"], customer["id"], index)

    resp = await client.get("/api/v1/analytics/chitti/overview", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["kpis"]["total_members"] == 3
    metric = next(m for m in data["chitti_metrics"] if m["id"] == chitti["id"])
    assert metric["member_count"] == 3
    assert metric["active_members"] == 0
    for value in (
        data["kpis"]["total_collected"],
        data["kpis"]["total_pending"],
        data["kpis"]["collection_efficiency"],
        metric["pending"],
        metric["collection_pct"],
    ):
        assert math.isfinite(value)


@pytest.mark.asyncio
async def test_activation_requires_members(client, test_user):
    """A chitti with no members reports NO_MEMBERS and stays DRAFT."""
    headers = _auth(test_user)
    plan = await _make_plan(client, headers)
    chitti = await _make_chitti(client, headers, plan["id"], name="Empty Chitti")

    activation = (
        await client.get(f"/api/v1/chitti/{chitti['id']}/activation", headers=headers)
    ).json()["data"]
    assert activation["can_activate"] is False
    codes = {b["code"] for b in activation["blockers"]}
    assert "NO_MEMBERS" in codes
    assert activation["enrolled_members"] == 0
    assert activation["available_slots"] == 10

    resp = await client.post(f"/api/v1/chitti/{chitti['id']}/start", headers=headers)
    assert resp.status_code == 400
    status = (await client.get(f"/api/v1/chitti/{chitti['id']}", headers=headers)).json()["data"]["status"]
    assert status == "DRAFT"


@pytest.mark.asyncio
async def test_dashboard_financials_are_finite_for_draft_chitti(client, test_user):
    """Pending money must never be reported from unmaterialised schedule rows."""
    headers = _auth(test_user)
    plan = await _make_plan(client, headers)
    chitti = await _make_chitti(client, headers, plan["id"], name="Finite Chitti")

    item = next(
        i
        for i in (await client.get("/api/v1/chitti/dashboard", headers=headers)).json()["data"]
        if i["id"] == chitti["id"]
    )
    assert item["financials_source"] == "not_generated"
    assert item["expected_collection"] == 0.0
    assert item["pending_collection"] == 0.0
    _assert_finite(item)
