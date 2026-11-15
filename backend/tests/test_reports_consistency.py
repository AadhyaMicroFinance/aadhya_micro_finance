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
from io import BytesIO, StringIO
from datetime import date

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.payment import PaymentTransaction

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


@pytest.mark.asyncio
async def test_reversal_restores_schedule_and_report(client, test_user, db_session):
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

    reversal = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{original_id}/reverse",
        json={"reversal_reason": "regression reversal"}, headers=headers,
    )
    assert reversal.status_code == 200, reversal.text
    assert reversal.json()["data"]["duplicate"] is False
    repeated = await client.post(
        f"/api/v1/chitti/{chitti['id']}/transactions/{original_id}/reverse",
        json={"reversal_reason": "retry"}, headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["duplicate"] is True

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
