"""Regression tests for editable finance-account metadata."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from tests.finance_helpers import create_finance_account


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _create_account(client, headers):
    customer = await client.post(
        "/api/v1/customers/",
        json={
            "full_name": "Finance Update Customer",
            "mobile_number": "9440000001",
            "address": "Hyderabad, Telangana",
        },
        headers=headers,
    )
    assert customer.status_code == 200, customer.text

    account, _ = await create_finance_account(
        client,
        headers,
        customer.json()["data"]["id"],
        frequency="WEEKLY",
        number_of_installments=3,
    )
    return account


@pytest.mark.asyncio
async def test_finance_update_persists_metadata_without_touching_financial_state(
    client, test_user, db_session
):
    headers = _auth(test_user)
    account = await _create_account(client, headers)
    before = (await client.get(
        f"/api/v1/finance/{account['id']}/schedule", headers=headers
    )).json()["data"]

    response = await client.put(
        f"/api/v1/finance/{account['id']}",
        json={"status": "CLOSED", "notes": "Reviewed at closing"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    updated = response.json()["data"]
    assert updated["status"] == "CLOSED"
    assert updated["notes"] == "Reviewed at closing"
    assert updated["principal_amount"] == account["principal_amount"]
    assert updated["total_payable"] == account["total_payable"]
    assert updated["installment_amount"] == account["installment_amount"]

    after = (await client.get(
        f"/api/v1/finance/{account['id']}/schedule", headers=headers
    )).json()["data"]
    assert after == before

    audit = (await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "FINANCE_ACCOUNT",
            AuditLog.entity_id == UUID(account["id"]),
            AuditLog.action == "FINANCE_UPDATED",
        ).order_by(AuditLog.created_at.desc())
    )).scalars().first()
    assert audit is not None
    assert audit.previous_value["status"] == "ACTIVE"
    assert audit.new_value["status"] == "CLOSED"


@pytest.mark.asyncio
async def test_finance_update_validates_status_and_missing_account(
    client, test_user
):
    headers = _auth(test_user)
    account = await _create_account(client, headers)

    invalid = await client.put(
        f"/api/v1/finance/{account['id']}",
        json={"status": "NOT_A_STATUS"},
        headers=headers,
    )
    assert invalid.status_code == 422

    missing = await client.put(
        f"/api/v1/finance/{uuid4()}",
        json={"notes": "No such account"},
        headers=headers,
    )
    assert missing.status_code == 404
