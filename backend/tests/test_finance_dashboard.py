"""Finance-only dashboard, listing and collections projections."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.models.chitti import ChittiTransaction
from tests.finance_helpers import auth, create_finance_account, generate_agreement

PLAN = {
    "name": "Dashboard Noise Plan",
    "chitti_type": "FIXED",
    "total_value": "10000.00",
    "member_count": 1,
    "frequency": "DAILY",
    "duration": 1,
    "contribution_rules": {
        "type": "FIXED",
        "installment_amount": "1000.00",
        "partial_payments_allowed": True,
    },
    "payout_rules": {"type": "SCHEDULED"},
}


async def _customer(client, headers, name, mobile):
    response = await client.post(
        "/api/v1/customers/",
        json={"full_name": name, "mobile_number": mobile, "address": "Hyderabad"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _seed_chitti_money(client, headers, db_session, amount="777.00"):
    """Create a Chitti ledger row that must never leak into Finance KPIs."""
    plan = (
        await client.post("/api/v1/chitti/plans", json=PLAN, headers=headers)
    ).json()["data"]
    chitti = (
        await client.post(
            "/api/v1/chitti/",
            json={
                "plan_id": plan["id"],
                "name": "Dashboard Noise Chitti",
                "member_count": 1,
                "start_date": date.today().isoformat(),
            },
            headers=headers,
        )
    ).json()["data"]
    transaction = ChittiTransaction(
        chitti_id=UUID(chitti["id"]),
        transaction_type="CONTRIBUTION",
        amount=Decimal(amount),
        payment_method="CASH",
        payment_date=date.today(),
        idempotency_key=f"dashboard-chitti-noise-{uuid4()}",
    )
    db_session.add(transaction)
    await db_session.flush()
    return transaction


async def _pay(client, headers, customer_id, account_id, schedule_id, amount, key, payment_date):
    response = await client.post(
        "/api/v1/payments/",
        json={
            "customer_id": customer_id,
            "finance_account_id": account_id,
            "finance_schedule_id": schedule_id,
            "amount": amount,
            "payment_method": "CASH",
            "payment_date": payment_date,
            "idempotency_key": key,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_finance_dashboard_kpis_ignore_chitti_rows(client, test_user, db_session):
    headers = auth(test_user)
    overdue_customer = await _customer(client, headers, "Dashboard Overdue Payer", "9620000001")
    future_customer = await _customer(client, headers, "Dashboard Future Payer", "9620000002")

    overdue_account, _ = await create_finance_account(
        client,
        headers,
        overdue_customer["id"],
        principal_amount="3000.00",
        frequency="DAILY",
        number_of_installments=2,
        first_due_date=(date.today() - timedelta(days=10)).isoformat(),
    )
    future_account, _ = await create_finance_account(
        client,
        headers,
        future_customer["id"],
        principal_amount="2000.00",
        frequency="DAILY",
        number_of_installments=1,
        first_due_date=(date.today() + timedelta(days=5)).isoformat(),
    )
    schedule = (
        await client.get(
            f"/api/v1/finance/{overdue_account['id']}/schedule", headers=headers
        )
    ).json()["data"]
    await _pay(
        client,
        headers,
        overdue_customer["id"],
        overdue_account["id"],
        schedule[0]["id"],
        "500.00",
        "dashboard-finance-payment-1",
        date.today().isoformat(),
    )
    await _seed_chitti_money(client, headers, db_session)

    response = await client.get("/api/v1/finance/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    kpis = data["kpis"]

    assert kpis["total_accounts"] == 2
    assert kpis["total_principal_disbursed"] == 5000.0
    assert kpis["total_outstanding"] == 4500.0
    assert kpis["total_collections"] == 500.0  # Chitti's 777 is excluded
    assert kpis["pending_repayments"] == 2500.0
    assert kpis["overdue_repayments"] == 2500.0
    assert kpis["pending_repayments_count"] == 2
    assert kpis["overdue_repayments_count"] == 2
    assert kpis["overdue_accounts_count"] == 1
    assert kpis["total_collections_count"] == 1
    assert data["status_distribution"] == [{"status": "ACTIVE", "count": 2}]

    assert any(item["period"] == date.today().isoformat()[:7] for item in data["trends"])
    current = next(item for item in data["trends"] if item["period"] == date.today().isoformat()[:7])
    assert current["collected"] >= 500.0
    assert len(data["upcoming_repayments"]) == 1
    assert data["upcoming_repayments"][0]["account_id"] == future_account["id"]
    assert len(data["overdue_accounts"]) == 1
    assert data["overdue_accounts"][0]["account_id"] == overdue_account["id"]
    assert data["overdue_accounts"][0]["overdue_amount"] == 2500.0
    assert all(item["type"] == "PAYMENT" for item in data["recent_activity"])
    assert len(data["recent_activity"]) == 1


@pytest.mark.asyncio
async def test_finance_listing_search_filter_and_agreement_status(client, test_user, db_session):
    headers = auth(test_user)
    first = await _customer(client, headers, "Listing Alpha Customer", "9620000011")
    second = await _customer(client, headers, "Listing Beta Customer", "9620000012")
    first_account, _ = await create_finance_account(client, headers, first["id"])
    second_account, _ = await create_finance_account(client, headers, second["id"])

    # A generated-but-unlinked agreement must not create a phantom account.
    await generate_agreement(client, headers, first["id"])

    listing = (await client.get("/api/v1/finance/", headers=headers)).json()
    assert listing["meta"]["total"] == 2
    for item in listing["data"]:
        assert item["customer_name"]
        assert item["customer_code"]
        assert item["mobile_number"]
        assert item["agreement_status"] == "CONFIRMED"

    for query, expected_id in (
        ("Alpha", first_account["id"]),
        ("9620000012", second_account["id"]),
        (first_account["account_number"], first_account["id"]),
    ):
        found = (await client.get(
            "/api/v1/finance/", params={"search": query}, headers=headers
        )).json()
        assert found["meta"]["total"] == 1
        assert found["data"][0]["id"] == expected_id

    confirmed = (await client.get(
        "/api/v1/finance/", params={"agreement_status": "CONFIRMED"}, headers=headers
    )).json()
    assert confirmed["meta"]["total"] == 2
    none = (await client.get(
        "/api/v1/finance/", params={"agreement_status": "NONE"}, headers=headers
    )).json()
    assert none["meta"]["total"] == 0
    generated = (await client.get(
        "/api/v1/finance/", params={"agreement_status": "GENERATED"}, headers=headers
    )).json()
    assert generated["meta"]["total"] == 0

    page_two = (await client.get(
        "/api/v1/finance/", params={"page": 2, "per_page": 1}, headers=headers
    )).json()
    assert page_two["meta"] == {"page": 2, "per_page": 1, "total": 2, "total_pages": 2}
    assert len(page_two["data"]) == 1


@pytest.mark.asyncio
async def test_finance_collections_are_finance_only_and_filterable(client, test_user, db_session):
    headers = auth(test_user)
    first = await _customer(client, headers, "Collection Alpha Customer", "9620000021")
    second = await _customer(client, headers, "Collection Beta Customer", "9620000022")
    first_account, _ = await create_finance_account(
        client, headers, first["id"], first_due_date=date.today().isoformat()
    )
    second_account, _ = await create_finance_account(
        client, headers, second["id"], first_due_date=date.today().isoformat()
    )
    first_schedule = (
        await client.get(f"/api/v1/finance/{first_account['id']}/schedule", headers=headers)
    ).json()["data"][0]
    second_schedule = (
        await client.get(f"/api/v1/finance/{second_account['id']}/schedule", headers=headers)
    ).json()["data"][0]

    today_payment = await _pay(
        client, headers, first["id"], first_account["id"], first_schedule["id"],
        "3000.00", "collections-today-1", date.today().isoformat(),
    )
    yesterday_payment = await _pay(
        client, headers, second["id"], second_account["id"], second_schedule["id"],
        "2000.00", "collections-yesterday-1", (date.today() - timedelta(days=1)).isoformat(),
    )
    await _seed_chitti_money(client, headers, db_session)

    all_collections = (await client.get("/api/v1/finance/collections", headers=headers)).json()
    assert all_collections["meta"]["total"] == 2
    assert len(all_collections["data"]) == 2
    for item in all_collections["data"]:
        assert set(item) >= {
            "id", "transaction_id", "customer_id", "customer_name", "finance_account_id",
            "account_number", "installment_number", "amount", "payment_method",
            "payment_date", "status", "is_reversal", "collected_by", "created_at",
        }
        assert item["finance_account_id"] in (first_account["id"], second_account["id"])
        assert item["account_number"]
    assert {item["transaction_id"] for item in all_collections["data"]} == {
        today_payment["transaction_id"], yesterday_payment["transaction_id"]
    }

    by_customer = (await client.get(
        "/api/v1/finance/collections", params={"customer_id": first["id"]}, headers=headers
    )).json()
    assert by_customer["meta"]["total"] == 1
    assert by_customer["data"][0]["finance_account_id"] == first_account["id"]

    by_account = (await client.get(
        "/api/v1/finance/collections",
        params={"finance_account_id": second_account["id"]},
        headers=headers,
    )).json()
    assert by_account["meta"]["total"] == 1

    from_today = (await client.get(
        "/api/v1/finance/collections",
        params={"date_from": date.today().isoformat()},
        headers=headers,
    )).json()
    assert from_today["meta"]["total"] == 1
    assert from_today["data"][0]["transaction_id"] == today_payment["transaction_id"]

    until_yesterday = (await client.get(
        "/api/v1/finance/collections",
        params={"date_to": (date.today() - timedelta(days=1)).isoformat()},
        headers=headers,
    )).json()
    assert until_yesterday["meta"]["total"] == 1
    assert until_yesterday["data"][0]["transaction_id"] == yesterday_payment["transaction_id"]

    by_account_number = (await client.get(
        "/api/v1/finance/collections",
        params={"search": first_account["account_number"]},
        headers=headers,
    )).json()
    assert by_account_number["meta"]["total"] == 1

    second_page = (await client.get(
        "/api/v1/finance/collections",
        params={"page": 2, "per_page": 1},
        headers=headers,
    )).json()
    assert second_page["meta"]["total"] == 2
    assert len(second_page["data"]) == 1

    pending = (await client.get("/api/v1/finance/collections/pending", headers=headers)).json()
    assert pending["data"]
    assert all(item["source"] == "FINANCE" for item in pending["data"])
    # The first installment was fully paid, so only the second account is due.
    assert {item["account_id"] for item in pending["data"]} == {second_account["id"]}
