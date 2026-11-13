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
from datetime import date

import pytest

PLAN = {
    "name": "Report Consistency Plan",
    "chitti_type": "FIXED",
    "total_value": "10000.00",
    "member_count": 4,
    "frequency": "WEEKLY",
    "duration": 10,
    "contribution_rules": {"type": "FIXED", "installment_amount": "1000.00"},
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


async def _running_chitti(client, headers, members=2):
    """Create a chitti, sign every agreement and start it."""
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
        for action in ("generate", "print", "confirm"):
            resp = await client.post(
                f"/api/v1/chitti/{chitti['id']}/members/{member['id']}/agreement/{action}",
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
        enrolled.append(member)

    started = await client.post(f"/api/v1/chitti/{chitti['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    return chitti, enrolled


@pytest.mark.asyncio
async def test_reversal_restores_schedule_and_report(client, test_user):
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

    payment = (
        await client.post(
            "/api/v1/payments/",
            json={
                "customer_id": customer["id"],
                "finance_account_id": account["id"],
                "finance_schedule_id": installment["id"],
                "amount": "1000.00",
                "payment_method": "CASH",
                "payment_date": today,
                "idempotency_key": "reversal-test-1",
            },
            headers=headers,
        )
    ).json()["data"]

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
