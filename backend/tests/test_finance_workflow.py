"""End-to-end regressions for the Finance-only workflow."""

from datetime import date
from uuid import uuid4

import pytest

from tests.finance_helpers import create_finance_account, prepare_agreement


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _create_customer(client, headers, *, full_name: str, mobile: str):
    response = await client.post(
        "/api/v1/customers/",
        json={
            "full_name": full_name,
            "mobile_number": mobile,
            "address": "Hyderabad, Telangana",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_account(client, headers, customer_id: str, *, installments: int = 1):
    account, _ = await create_finance_account(
        client, headers, customer_id, number_of_installments=installments
    )
    return account


async def _record_payment(client, headers, *, customer_id, account_id, schedule_id, amount, key):
    return await client.post(
        "/api/v1/payments/",
        json={
            "customer_id": customer_id,
            "finance_account_id": account_id,
            "finance_schedule_id": schedule_id,
            "amount": str(amount),
            "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
            "idempotency_key": key,
        },
        headers=headers,
    )


@pytest.mark.asyncio
async def test_finance_customer_search_matches_name_and_mobile(client, test_user):
    headers = _auth(test_user)
    customer = await _create_customer(
        client, headers, full_name="Finance Search Test1", mobile="9000000098"
    )

    for query in ("Test1", "9000000098"):
        response = await client.get(
            "/api/v1/customers/",
            params={"search": query, "status": "ACTIVE", "per_page": 50},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        matches = response.json()["data"]
        assert [item["id"] for item in matches] == [customer["id"]]
        assert matches[0]["customer_code"] == customer["customer_code"]
        assert matches[0]["mobile_number"] == "9000000098"


@pytest.mark.asyncio
async def test_finance_create_validates_customer_and_list_exposes_identity(client, test_user):
    headers = _auth(test_user)
    customer = await _create_customer(
        client, headers, full_name="Finance Identity Customer", mobile="9440000011"
    )

    agreement, payload = await prepare_agreement(client, headers, customer["id"])
    missing = await client.post(
        "/api/v1/finance/",
        json={
            **payload,
            "customer_id": str(uuid4()),
            "agreement_id": agreement["agreement_id"],
        },
        headers=headers,
    )
    assert missing.status_code == 404, missing.text

    account = await _create_account(client, headers, customer["id"])
    assert account["customer_name"] == customer["full_name"]
    assert account["customer_code"] == customer["customer_code"]
    assert account["mobile_number"] == customer["mobile_number"]

    detail = await client.get(f"/api/v1/finance/{account['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["customer_name"] == customer["full_name"]

    listing = await client.get("/api/v1/finance/", headers=headers)
    assert listing.status_code == 200, listing.text
    listed = listing.json()["data"]
    assert len(listed) == 1
    assert listed[0]["customer_name"] == customer["full_name"]
    assert listed[0]["customer_code"] == customer["customer_code"]

    malformed = await client.get(
        "/api/v1/finance/", params={"customer_id": "not-a-uuid"}, headers=headers
    )
    assert malformed.status_code == 422


@pytest.mark.asyncio
async def test_finance_partial_repayment_updates_due_balance_and_history(client, test_user):
    headers = _auth(test_user)
    customer = await _create_customer(
        client, headers, full_name="Finance Repayment Customer", mobile="9440000012"
    )
    account = await _create_account(client, headers, customer["id"])

    schedule_response = await client.get(
        f"/api/v1/finance/{account['id']}/schedule", headers=headers
    )
    schedule = schedule_response.json()["data"]
    assert len(schedule) == 1
    installment = schedule[0]
    assert installment["expected_amount"] == 3000

    partial = await _record_payment(
        client,
        headers,
        customer_id=customer["id"],
        account_id=account["id"],
        schedule_id=installment["id"],
        amount="1000",
        key="finance-workflow-partial-1",
    )
    assert partial.status_code == 200, partial.text

    after_partial = (await client.get(
        f"/api/v1/finance/{account['id']}/schedule", headers=headers
    )).json()["data"][0]
    assert after_partial["paid_amount"] == 1000
    assert after_partial["remaining_amount"] == 2000
    assert after_partial["status"] == "PARTIALLY_PAID"

    due = (await client.get(
        f"/api/v1/payments/due/{customer['id']}",
        params={"finance_account_id": account["id"]},
        headers=headers,
    )).json()["data"]
    assert due["amount_due"] == 2000
    assert due["outstanding"] == 2000
    assert due["total_paid"] == 1000
    assert due["next_installment_number"] == 1

    history = (await client.get(
        "/api/v1/payments/",
        params={"finance_account_id": account["id"]},
        headers=headers,
    )).json()
    assert history["meta"]["total"] == 1
    assert history["data"][0]["account_type"] == "FINANCE"
    assert history["data"][0]["installment_number"] == 1
    assert history["data"][0]["finance_account_id"] == account["id"]

    final = await _record_payment(
        client,
        headers,
        customer_id=customer["id"],
        account_id=account["id"],
        schedule_id=installment["id"],
        amount="2000",
        key="finance-workflow-partial-2",
    )
    assert final.status_code == 200, final.text

    paid_installment = (await client.get(
        f"/api/v1/finance/{account['id']}/schedule", headers=headers
    )).json()["data"][0]
    assert paid_installment["status"] == "PAID"
    assert paid_installment["remaining_amount"] == 0

    settled = (await client.get(
        f"/api/v1/payments/due/{customer['id']}",
        params={"finance_account_id": account["id"]},
        headers=headers,
    )).json()["data"]
    assert settled["amount_due"] == 0
    assert settled["outstanding"] == 0
    assert settled["total_paid"] == 3000


@pytest.mark.asyncio
async def test_finance_due_info_does_not_expose_another_customers_account(client, test_user):
    headers = _auth(test_user)
    owner = await _create_customer(
        client, headers, full_name="Finance Due Owner", mobile="9440000013"
    )
    other = await _create_customer(
        client, headers, full_name="Finance Due Other", mobile="9440000014"
    )
    account = await _create_account(client, headers, owner["id"])

    response = await client.get(
        f"/api/v1/payments/due/{other['id']}",
        params={"finance_account_id": account["id"]},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
