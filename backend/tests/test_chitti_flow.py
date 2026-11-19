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
import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.chitti_service import ChittiService

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

    # Business rule: one signed member is NOT enough — every enrolled member
    # must sign before the chitti may start.
    activation_partial = (
        await client.get(f"/api/v1/chitti/{chitti_id}/activation", headers=headers)
    ).json()["data"]
    assert activation_partial["active_members"] == 1
    assert activation_partial["pending_agreements"] == 9
    assert activation_partial["can_activate"] is False
    assert "AGREEMENTS_PENDING" in {b["code"] for b in activation_partial["blockers"]}
    assert activation_partial["warnings"] == []

    partial_start = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert partial_start.status_code == 400, partial_start.text
    assert partial_start.json()["error"]["code"] == "ACTIVATION_BLOCKED"
    assert "AGREEMENTS_PENDING" in {
        b["code"] for b in partial_start.json()["error"]["details"]["blockers"]
    }
    dash_partial = next(
        i
        for i in (await client.get("/api/v1/chitti/dashboard", headers=headers)).json()["data"]
        if i["id"] == chitti_id
    )
    assert dash_partial["display_state"] == "ACTIVATION_BLOCKED"
    assert dash_partial["pending_agreements"] == 9

    # Sign every remaining agreement, then the chitti becomes startable.
    final_confirmation = None
    for member in members[1:]:
        final_confirmation = await _activate_member(client, headers, chitti_id, member["id"])

    # Final agreement confirmation activates the member but leaves the Chitti
    # ready until the operator invokes the explicit manual Start action.
    assert final_confirmation["chitti_auto_started"] is False
    assert final_confirmation["chitti_status"] == "DRAFT"

    persisted = (await client.get(f"/api/v1/chitti/{chitti_id}", headers=headers)).json()["data"]
    assert persisted["status"] == "DRAFT"
    ready = (await client.get(f"/api/v1/chitti/{chitti_id}/activation", headers=headers)).json()["data"]
    assert ready["can_activate"] is True
    manual_start = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert manual_start.status_code == 200, manual_start.text
    assert manual_start.json()["data"]["status"] == "RUNNING"

    schedule = (await client.get(f"/api/v1/chitti/{chitti_id}/schedule", headers=headers)).json()["data"]
    assert len(schedule) == 10
    for member in members:
        contributions = (
            await client.get(
                f"/api/v1/chitti/{chitti_id}/members/{member['id']}/contributions",
                headers=headers,
            )
        ).json()["data"]
        assert len(contributions) == 10

    # A repeated schedule synchronization through the already-guarded start
    # service cannot duplicate either contribution or period rows. Since the
    # Chitti is RUNNING, the normal start API correctly rejects this request.
    duplicate_start = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert duplicate_start.status_code == 400
    schedule_after = (await client.get(f"/api/v1/chitti/{chitti_id}/schedule", headers=headers)).json()["data"]
    assert len(schedule_after) == len(schedule)

    dashboard_after = (await client.get("/api/v1/chitti/dashboard", headers=headers)).json()["data"]
    item_after = next(i for i in dashboard_after if i["id"] == chitti_id)
    assert item_after["status"] == "RUNNING"
    assert item_after["member_count"] == 10

    summary_after = (await client.get(f"/api/v1/chitti/{chitti_id}/summary", headers=headers)).json()["data"]
    assert summary_after["display_state"] == "ACTIVE"
    assert summary_after["activation"]["can_activate"] is False
    assert summary_after["financials_source"] == "contributions"
    # 10 members x 10 weekly installments of 1000 => 100,000 expected.
    assert summary_after["expected_collection"] == 100000.0
    assert summary_after["actual_collection"] == 0.0
    assert summary_after["pending_collection"] == 100000.0

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


@pytest.mark.asyncio
async def test_saved_fixed_plan_overrides_recalculate_preview_and_instance(client, test_user):
    headers = _auth(test_user)
    plan_payload = {
        "name": "Reusable fixed plan", "chitti_type": "FIXED", "total_value": "2800",
        "member_count": 2, "frequency": "DAILY", "duration": 14,
        "contribution_rules": {"type": "FIXED", "installment_amount": "100"},
        "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
    }
    created_plan = await client.post("/api/v1/chitti/plans", json=plan_payload, headers=headers)
    assert created_plan.status_code == 200, created_plan.text
    plan = created_plan.json()["data"]
    overrides = {
        "start_date": date.today().isoformat(), "member_count": 3,
        "frequency": "WEEKLY", "duration": 30,
        "contribution_rules": {"type": "FIXED", "installment_amount": "200"},
    }
    preview = await client.post(f"/api/v1/chitti/plans/{plan['id']}/preview", json={"plan_id": plan["id"], **overrides}, headers=headers)
    assert preview.status_code == 200, preview.text
    assert Decimal(str(preview.json()["data"]["total_value"])) == Decimal("18000.00")
    assert len(preview.json()["data"]["periods"]) == 30

    instance = await client.post("/api/v1/chitti/", json={
        **overrides, "plan_id": plan["id"], "name": "Overridden instance",
    }, headers=headers)
    assert instance.status_code == 200, instance.text
    assert Decimal(str(instance.json()["data"]["total_value"])) == Decimal("18000.00")
    schedule = (await client.get(
        f"/api/v1/chitti/{instance.json()['data']['id']}/schedule", headers=headers
    )).json()["data"]
    assert len(schedule) == 30
    assert schedule[0]["due_date"] == date.today().isoformat()
    reread_plan = (await client.get(f"/api/v1/chitti/plans/{plan['id']}", headers=headers)).json()["data"]
    assert Decimal(str(reread_plan["total_value"])) == Decimal("2800.00")


@pytest.mark.asyncio
async def test_lift_management_is_separate_from_payout_and_reversible(client, test_user):
    """Only an explicit lift event applies surcharge; payout alone does not."""
    headers = _auth(test_user)
    plan_payload = {
        "name": "Lift Surcharge Daily",
        "chitti_type": "LIFT_BASED",
        "total_value": "120000.00",
        "member_count": 1,
        "frequency": "DAILY",
        "duration": 4,
        "contribution_rules": {"type": "LIFT_BASED", "regular_amount": "5000.00"},
        "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
    }
    plan_response = await client.post(
        "/api/v1/chitti/plans", json=plan_payload, headers=headers
    )
    assert plan_response.status_code == 200, plan_response.text
    plan = plan_response.json()["data"]
    chitti = await _make_chitti(client, headers, plan["id"], name="Lift Surcharge Test")
    customer = (await _make_customers(client, headers, 1))[0]
    member = await _enroll(client, headers, chitti["id"], customer["id"], 1)
    await _activate_member(client, headers, chitti["id"], member["id"])
    started = await client.post(f"/api/v1/chitti/{chitti['id']}/start", headers=headers)
    assert started.status_code == 200, started.text

    before = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/schedule", headers=headers
    )).json()["data"]
    assert [float(row["expected_collection"]) for row in before] == [5000] * 4

    payout_response = await client.post(
        f"/api/v1/chitti/{chitti['id']}/payouts",
        json={
            "member_id": member["id"],
            "period_number": 2,
            "gross_payout": "10000.00",
            "discount_amount": "0.00",
            "fee_amount": "0.00",
            "net_payout": "10000.00",
            "payout_method": "CASH",
        },
        headers=headers,
    )
    assert payout_response.status_code == 200, payout_response.text

    member_data = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/members", headers=headers
    )).json()["data"][0]
    assert member_data["lifted"] is False
    assert member_data["total_expected"] == 20000
    updated_schedule = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/schedule", headers=headers
    )).json()["data"]
    assert [float(row["expected_collection"]) for row in updated_schedule] == [5000] * 4
    assert float(updated_schedule[1]["actual_payout"]) == 10000

    lift_response = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts",
        json={"member_id": member["id"], "period_number": 1, "lift_date": date.today().isoformat()},
        headers=headers,
    )
    assert lift_response.status_code == 200, lift_response.text
    lift_id = lift_response.json()["data"]["id"]
    assert (await client.get(f"/api/v1/chitti/{chitti['id']}/lifts", headers=headers)).json()["data"][0]["period_number"] == 1
    duplicate_lift = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts",
        json={"member_id": member["id"], "period_number": 1, "lift_date": date.today().isoformat()},
        headers=headers,
    )
    assert duplicate_lift.status_code == 409
    member_data = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/members", headers=headers
    )).json()["data"][0]
    assert member_data["lifted"] is True
    assert member_data["lift_period"] == 1
    assert member_data["total_expected"] == 23600
    updated_schedule = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/schedule", headers=headers
    )).json()["data"]
    assert [float(row["expected_collection"]) for row in updated_schedule] == [5000, 6200, 6200, 6200]

    collection_response = await client.post(
        f"/api/v1/chitti/{chitti['id']}/contributions",
        json={
            "member_id": member["id"],
            "period_number": 1,
            "amount": "5000.00",
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": "lift-period-one-payment",
        },
        headers=headers,
    )
    assert collection_response.status_code == 200, collection_response.text
    member_after_collection = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/members", headers=headers
    )).json()["data"][0]
    assert member_after_collection["total_paid"] == 5000
    assert member_after_collection["outstanding"] == 18600
    today_report = (await client.get(
        f"/api/v1/reports/daily?date={date.today().isoformat()}", headers=headers
    )).json()["data"]
    assert today_report["chitti_collected"] == 5000

    reversal = await client.post(
        f"/api/v1/chitti/{chitti['id']}/lifts/{lift_id}/reverse",
        json={"reversal_reason": "Recorded in error"}, headers=headers,
    )
    assert reversal.status_code == 200, reversal.text
    member_after_reversal = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/members", headers=headers
    )).json()["data"][0]
    assert member_after_reversal["lifted"] is False
    assert member_after_reversal["total_paid"] == 5000
    assert member_after_reversal["outstanding"] == 15000
    schedule_after_lift_reversal = (await client.get(
        f"/api/v1/chitti/{chitti['id']}/schedule", headers=headers
    )).json()["data"]
    assert [float(row["expected_collection"]) for row in schedule_after_lift_reversal] == [5000] * 4
    assert [float(row["pending_collection"]) for row in schedule_after_lift_reversal] == [0.0, 5000.0, 5000.0, 5000.0]


@pytest.mark.asyncio
async def test_partial_contribution_settles_only_remaining_balance(client, test_user):
    headers = _auth(test_user)
    plan_response = await client.post("/api/v1/chitti/plans", json={
        "name": "Partial payment test", "chitti_type": "FIXED", "total_value": "100.00",
        "member_count": 1, "frequency": "DAILY", "duration": 1,
        "contribution_rules": {"type": "FIXED", "installment_amount": "100.00", "partial_payments_allowed": True},
        "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
    }, headers=headers)
    assert plan_response.status_code == 200, plan_response.text
    chitti_response = await client.post("/api/v1/chitti/", json={
        "plan_id": plan_response.json()["data"]["id"], "name": "Partial payment chitti",
        "member_count": 1, "start_date": date.today().isoformat(),
    }, headers=headers)
    assert chitti_response.status_code == 200, chitti_response.text
    chitti_id = chitti_response.json()["data"]["id"]
    customer = (await _make_customers(client, headers, 1))[0]
    member = await _enroll(client, headers, chitti_id, customer["id"], 1)
    await _activate_member(client, headers, chitti_id, member["id"])
    started = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    base = {"member_id": member["id"], "period_number": 1, "payment_method": "UPI", "payment_date": date.today().isoformat()}
    first = await client.post(f"/api/v1/chitti/{chitti_id}/contributions", json={
        **base, "amount": "40.00", "idempotency_key": "partial-40",
    }, headers=headers)
    assert first.status_code == 200, first.text
    retry = await client.post(f"/api/v1/chitti/{chitti_id}/contributions", json={
        **base, "amount": "40.00", "idempotency_key": "partial-40",
    }, headers=headers)
    assert retry.status_code == 200, retry.text
    assert retry.json()["data"]["duplicate"] is True
    second = await client.post(f"/api/v1/chitti/{chitti_id}/contributions", json={
        **base, "amount": "60.00", "idempotency_key": "partial-60",
    }, headers=headers)
    assert second.status_code == 200, second.text
    overpay = await client.post(f"/api/v1/chitti/{chitti_id}/contributions", json={
        **base, "amount": "1.00", "idempotency_key": "after-settlement",
    }, headers=headers)
    assert overpay.status_code == 400
    assert overpay.json()["error"]["code"] == "CONTRIBUTION_PERIOD_ALREADY_PAID"
    history = await client.get("/api/v1/payments/", params={"per_page": 100}, headers=headers)
    chitti_receipts = [row for row in history.json()["data"] if row.get("chitti_account_id") == chitti_id]
    assert len(chitti_receipts) == 2


@pytest.mark.asyncio
async def test_concurrent_full_payments_cannot_overcollect(client, test_user, test_engine, db_session):
    headers = _auth(test_user)
    plan_response = await client.post("/api/v1/chitti/plans", json={
        "name": "Concurrent payment test", "chitti_type": "FIXED", "total_value": "100.00",
        "member_count": 1, "frequency": "DAILY", "duration": 1,
        "contribution_rules": {"type": "FIXED", "installment_amount": "100.00"},
        "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
    }, headers=headers)
    assert plan_response.status_code == 200, plan_response.text
    chitti_response = await client.post("/api/v1/chitti/", json={
        "plan_id": plan_response.json()["data"]["id"], "name": "Concurrent collection",
        "member_count": 1, "start_date": date.today().isoformat(),
    }, headers=headers)
    assert chitti_response.status_code == 200, chitti_response.text
    chitti_id = chitti_response.json()["data"]["id"]
    customer = (await _make_customers(client, headers, 1))[0]
    member = await _enroll(client, headers, chitti_id, customer["id"], 1)
    await _activate_member(client, headers, chitti_id, member["id"])
    started = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    await db_session.commit()

    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def submit(key: str):
        async with sessions() as session:
            try:
                result = await ChittiService(session).record_contribution(
                    UUID(chitti_id), member_id=member["id"], period_number=1,
                    amount=Decimal("100.00"), payment_method="CASH",
                    payment_date=date.today(), idempotency_key=key,
                )
                await session.commit()
                return result
            except Exception as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(submit("concurrent-a"), submit("concurrent-b"))
    assert sum(isinstance(value, dict) for value in results) == 1
    assert sum(isinstance(value, Exception) for value in results) == 1
    history = await client.get("/api/v1/payments/", params={"per_page": 100}, headers=headers)
    chitti_receipts = [row for row in history.json()["data"] if row.get("chitti_account_id") == chitti_id]
    assert len(chitti_receipts) == 1


@pytest.mark.asyncio
async def test_two_chitti_payments_sync_history_schedule_progress_and_reports(client, test_user):
    """The shared Payments history includes the Chitti transaction ledger."""
    headers = _auth(test_user)
    plan_payload = {
        "name": "Two Member Daily Chitti",
        "chitti_type": "FIXED",
        "total_value": "2800.00",
        "member_count": 2,
        "frequency": "DAILY",
        "duration": 14,
        "contribution_rules": {
            "type": "FIXED",
            "installment_amount": "100.00",
            "partial_payments_allowed": True,
        },
        "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
    }
    plan_response = await client.post(
        "/api/v1/chitti/plans", json=plan_payload, headers=headers
    )
    assert plan_response.status_code == 200, plan_response.text
    chitti_response = await client.post(
        "/api/v1/chitti/",
        json={
            "plan_id": plan_response.json()["data"]["id"],
            "name": "Two Member Daily Chitti",
            "member_count": 2,
            "start_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert chitti_response.status_code == 200, chitti_response.text
    chitti_id = chitti_response.json()["data"]["id"]
    customers = await _make_customers(client, headers, 2)
    members = []
    for index, customer in enumerate(customers, start=1):
        member = await _enroll(client, headers, chitti_id, customer["id"], index)
        members.append(member)
    for member in members:
        await _activate_member(client, headers, chitti_id, member["id"])
    started = await client.post(f"/api/v1/chitti/{chitti_id}/start", headers=headers)
    assert started.status_code == 200, started.text

    for index, member in enumerate(members, start=1):
        response = await client.post(
            f"/api/v1/chitti/{chitti_id}/contributions",
            json={
                "member_id": member["id"],
                "period_number": 1,
                "amount": "100.00",
                "payment_method": "CASH",
                "payment_date": date.today().isoformat(),
                "idempotency_key": f"two-member-period-one-{index}",
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        if index == 1:
            partial_schedule = (await client.get(
                f"/api/v1/chitti/{chitti_id}/schedule", headers=headers
            )).json()["data"]
            assert partial_schedule[0]["status"] == "PARTIALLY_PAID"
            assert float(partial_schedule[0]["actual_collection"]) == 100
            assert float(partial_schedule[0]["pending_collection"]) == 100
            partial_summary = (await client.get(
                f"/api/v1/chitti/{chitti_id}/summary", headers=headers
            )).json()["data"]
            assert partial_summary["current_period"] == 0

    duplicate_full_payment = await client.post(
        f"/api/v1/chitti/{chitti_id}/contributions",
        json={"member_id": members[0]["id"], "period_number": 1, "amount": "100.00",
              "payment_method": "CASH", "payment_date": date.today().isoformat(),
              "idempotency_key": "new-key-after-period-settled"},
        headers=headers,
    )
    assert duplicate_full_payment.status_code == 400
    assert duplicate_full_payment.json()["error"]["code"] == "CONTRIBUTION_PERIOD_ALREADY_PAID"
    future_advance = await client.post(
        f"/api/v1/chitti/{chitti_id}/contributions",
        json={"member_id": members[0]["id"], "period_number": 2, "amount": "100.00",
              "payment_method": "CASH", "payment_date": date.today().isoformat(),
              "idempotency_key": "future-period-advance-block"},
        headers=headers,
    )
    assert future_advance.status_code == 400
    assert future_advance.json()["error"]["code"] == "CONTRIBUTION_PERIOD_NOT_DUE"

    history_response = await client.get(
        "/api/v1/payments/", params={"per_page": 100}, headers=headers
    )
    assert history_response.status_code == 200, history_response.text
    history = history_response.json()
    chitti_receipts = [
        payment for payment in history["data"]
        if payment.get("chitti_account_id") == chitti_id
    ]
    assert len(chitti_receipts) == 2
    assert {payment["amount"] for payment in chitti_receipts} == {100.0}
    assert {payment["period_number"] for payment in chitti_receipts} == {1}
    assert all(payment["transaction_id"].startswith("CHT-") for payment in chitti_receipts)
    assert len({payment["id"] for payment in chitti_receipts}) == 2

    schedule = (await client.get(
        f"/api/v1/chitti/{chitti_id}/schedule", headers=headers
    )).json()["data"]
    assert schedule[0]["status"] == "COMPLETED"
    assert float(schedule[0]["expected_collection"]) == 200
    assert float(schedule[0]["actual_collection"]) == 200
    assert float(schedule[0]["pending_collection"]) == 0
    assert schedule[0]["payout_schedule_available"] is True
    assert schedule[0]["scheduled_member_number"] == 1
    assert float(schedule[0]["expected_payout"]) == 200
    assert schedule[1]["status"] == "UPCOMING"
    assert schedule[1]["scheduled_member_number"] == 2
    assert float(schedule[1]["expected_payout"]) == 200

    summary = (await client.get(
        f"/api/v1/chitti/{chitti_id}/summary", headers=headers
    )).json()["data"]
    assert summary["current_period"] == 1

    # Projection is visible separately; it must not create a paid payout row.
    payouts = (await client.get(
        f"/api/v1/chitti/{chitti_id}/payouts", headers=headers
    )).json()["data"]
    assert payouts == []

    # The first installment is due today in the test; a fresh unpaid period
    # should show DUE, while the paid one above correctly shows COMPLETED.
    due_plan = {**plan_payload, "name": "Due status plan"}
    due_plan_response = await client.post(
        "/api/v1/chitti/plans", json=due_plan, headers=headers
    )
    assert due_plan_response.status_code == 200, due_plan_response.text
    due_chitti_response = await client.post(
        "/api/v1/chitti/",
        json={"plan_id": due_plan_response.json()["data"]["id"], "name": "Due today", "member_count": 2, "start_date": date.today().isoformat()},
        headers=headers,
    )
    assert due_chitti_response.status_code == 200, due_chitti_response.text
    due_chitti_id = due_chitti_response.json()["data"]["id"]
    due_schedule = (await client.get(
        f"/api/v1/chitti/{due_chitti_id}/schedule", headers=headers
    )).json()["data"]
    assert due_schedule[0]["status"] == "DUE"

    summary = (await client.get(
        f"/api/v1/chitti/{chitti_id}/summary", headers=headers
    )).json()["data"]
    assert summary["current_period"] == 1
    assert summary["total_periods"] == 14
    member_rows = (await client.get(
        f"/api/v1/chitti/{chitti_id}/members", headers=headers
    )).json()["data"]
    assert all(row["total_paid"] == 100 for row in member_rows)
    assert all(row["outstanding"] == 1300 for row in member_rows)

    for member in members:
        contributions = (await client.get(
            f"/api/v1/chitti/{chitti_id}/members/{member['id']}/contributions",
            headers=headers,
        )).json()["data"]
        assert len(contributions[0]["payments"]) == 1
        assert contributions[0]["payments"][0]["amount"] == 100

    eligible = (await client.get(
        f"/api/v1/payments/customer/{customers[0]['id']}/eligible-accounts",
        headers=headers,
    )).json()["data"]
    assert eligible["chitti_memberships"][0]["current_period"] == 2
    assert eligible["chitti_memberships"][0]["amount_due"] == 100

    chitti_dashboard = (await client.get(
        "/api/v1/chitti/dashboard", headers=headers
    )).json()["data"]
    dashboard_chitti = next(row for row in chitti_dashboard if row["id"] == chitti_id)
    assert dashboard_chitti["current_period"] == 1

    daily = (await client.get(
        f"/api/v1/reports/daily?date={date.today().isoformat()}", headers=headers
    )).json()["data"]
    assert daily["chitti_collected"] == 200
