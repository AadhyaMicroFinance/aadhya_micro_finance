"""Finance agreement workflow: generation, review, print, download, confirm."""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, inspect, select

from app.models.audit import AuditLog
from app.models.finance import FinanceAccount, FinanceAgreement
from app.services.calculation_engine import CalculationEngine
from app.services.finance_terms import compute_finance_terms_hash
from tests.finance_helpers import (
    CONFIRMATION_TEXT,
    auth,
    confirm_agreement,
    create_finance_account,
    generate_agreement,
    loan_payload,
    print_agreement,
)


async def _customer(client, headers, name, mobile):
    response = await client.post(
        "/api/v1/customers/",
        json={"full_name": name, "mobile_number": mobile, "address": "Hyderabad"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_generate_agreement_has_customer_loan_terms_snapshot_and_hash(
    client, test_user, db_session
):
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement Snapshot Customer", "9610000001")
    payload = loan_payload(
        customer["id"],
        principal_amount="12500.50",
        interest_rate="12",
        interest_type="FLAT",
        fees="250.00",
        frequency="MONTHLY",
        number_of_installments=4,
    )
    agreement, _ = await generate_agreement(client, headers, customer["id"], **{
        key: value for key, value in payload.items() if key != "customer_id"
    })

    assert agreement["agreement_id"]
    assert agreement["agreement_number"].startswith("FAGR-")
    assert agreement["status"] == "GENERATED"
    assert agreement["generated_at"]
    assert agreement["customer_name"] == customer["full_name"]
    assert agreement["customer_code"] == customer["customer_code"]
    assert agreement["mobile_number"] == customer["mobile_number"]

    calc = CalculationEngine()
    total, installment = calc.calculate_finance_totals(
        principal_amount=Decimal(payload["principal_amount"]),
        interest_rate=Decimal(payload["interest_rate"]),
        interest_type=payload["interest_type"],
        fees=Decimal(payload["fees"]),
        number_of_installments=payload["number_of_installments"],
        custom_installment_amount=None,
    )
    assert agreement["terms"]["principal_amount"] == 12500.50
    assert agreement["terms"]["interest_rate"] == 12.0
    assert agreement["terms"]["interest_type"] == "FLAT"
    assert agreement["terms"]["fees"] == 250.0
    assert agreement["terms"]["total_payable"] == float(total)
    assert agreement["terms"]["installment_amount"] == float(installment)
    assert agreement["terms"]["number_of_installments"] == 4
    assert len(agreement["schedule"]) == 4
    assert [row["installment_number"] for row in agreement["schedule"]] == [1, 2, 3, 4]
    assert all(row["expected_amount"] == float(installment) for row in agreement["schedule"])

    expected_hash = compute_finance_terms_hash(payload)
    assert agreement["terms_hash"] == expected_hash
    canonical = json.dumps(
        {
            "customer_id": customer["id"],
            "principal_amount": "12500.50",
            "interest_rate": "12.00",
            "interest_type": "FLAT",
            "fees": "250.00",
            "frequency": "MONTHLY",
            "start_date": payload["start_date"],
            "first_due_date": payload["first_due_date"],
            "number_of_installments": 4,
            "custom_installment_amount": None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert expected_hash == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    for fragment in (
        customer["full_name"],
        customer["customer_code"],
        customer["mobile_number"],
        "12500.50",
        "12",
        "250.00",
    ):
        assert fragment in agreement["agreement_html"]
        assert fragment in agreement["agreement_text"]
    assert "3000.00" not in agreement["agreement_html"]

    stored = (
        await db_session.execute(
            select(FinanceAgreement).where(
                FinanceAgreement.agreement_number == agreement["agreement_number"]
            )
        )
    ).scalar_one()
    assert stored.agreement_snapshot["customer"]["full_name"] == customer["full_name"]
    assert stored.agreement_snapshot["loan"]["principal_amount"] == "12500.50"
    assert stored.agreement_snapshot["terms"]["total_payable"] == str(total)
    assert len(stored.agreement_snapshot["schedule"]) == 4
    assert stored.finance_account_id is None
    assert await db_session.scalar(select(func.count()).select_from(FinanceAccount)) == 0


@pytest.mark.asyncio
async def test_review_and_print_increment_print_state(client, test_user):
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement Print Customer", "9610000002")
    agreement, _ = await generate_agreement(client, headers, customer["id"])

    review = await client.get(
        f"/api/v1/finance/agreements/{agreement['agreement_id']}", headers=headers
    )
    assert review.status_code == 200, review.text
    reviewed = review.json()["data"]
    assert reviewed["agreement_id"] == agreement["agreement_id"]
    assert reviewed["agreement_html"] == agreement["agreement_html"]
    assert reviewed["agreement_text"] == agreement["agreement_text"]
    assert reviewed["status"] == "GENERATED"

    first = await print_agreement(client, headers, agreement["agreement_id"])
    assert first["status"] == "PRINTED"
    assert first["print_count"] == 1
    assert first["printed_at"]
    assert first["agreement_html"] == agreement["agreement_html"]

    second = await print_agreement(client, headers, agreement["agreement_id"])
    assert second["status"] == "PRINTED"
    assert second["print_count"] == 2
    # Same instant, possibly represented in a different timezone after reload.
    assert datetime.fromisoformat(second["printed_at"]) == datetime.fromisoformat(
        first["printed_at"]
    )


@pytest.mark.asyncio
async def test_download_is_attachment_and_does_not_mutate_state(client, test_user):
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement Download Customer", "9610000003")
    agreement, _ = await generate_agreement(client, headers, customer["id"])
    await print_agreement(client, headers, agreement["agreement_id"])

    response = await client.get(
        f"/api/v1/finance/agreements/{agreement['agreement_id']}/download",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    assert agreement["agreement_number"] in response.headers["content-disposition"]
    assert customer["full_name"] in response.text
    assert response.headers["content-type"].startswith("text/html")

    review = (
        await client.get(
            f"/api/v1/finance/agreements/{agreement['agreement_id']}", headers=headers
        )
    ).json()["data"]
    assert review["status"] == "PRINTED"
    assert review["print_count"] == 1


@pytest.mark.asyncio
async def test_confirm_requires_exact_text_and_records_confirmation(client, test_user, db_session):
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement Confirm Customer", "9610000004")
    agreement, _ = await generate_agreement(client, headers, customer["id"])
    await print_agreement(client, headers, agreement["agreement_id"])

    wrong = await confirm_agreement(
        client, headers, agreement["agreement_id"], "I confirm the agreement"
    )
    assert wrong.status_code == 400, wrong.text
    assert wrong.json()["error"]["code"] == "AGREEMENT_CONFIRMATION_TEXT_MISMATCH"

    confirmed = await confirm_agreement(client, headers, agreement["agreement_id"])
    assert confirmed.status_code == 200, confirmed.text
    data = confirmed.json()["data"]
    assert data["agreement_id"] == agreement["agreement_id"]
    assert data["status"] == "CONFIRMED"
    assert data["confirmed_at"]
    assert data["confirmed_by"] == str(test_user["user"].id)

    stored = await db_session.get(
        FinanceAgreement, UUID(agreement["agreement_id"])
    )
    assert stored.agreement_status == "CONFIRMED"
    assert str(stored.confirmed_by) == str(test_user["user"].id)


@pytest.mark.asyncio
async def test_account_creation_requires_confirmed_agreement(client, test_user, db_session):
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement Unconfirmed Customer", "9610000005")
    payload = loan_payload(customer["id"])
    generated, _ = await generate_agreement(client, headers, customer["id"])
    await print_agreement(client, headers, generated["agreement_id"])

    unconfirmed = await client.post(
        "/api/v1/finance/",
        json={**payload, "agreement_id": generated["agreement_id"]},
        headers=headers,
    )
    assert unconfirmed.status_code == 400, unconfirmed.text
    assert unconfirmed.json()["error"]["code"] == "AGREEMENT_NOT_CONFIRMED"

    missing = await client.post(
        "/api/v1/finance/",
        json={**payload, "agreement_id": str(uuid4())},
        headers=headers,
    )
    assert missing.status_code == 400, missing.text
    assert missing.json()["error"]["code"] == "AGREEMENT_REQUIRED"

    no_id = await client.post("/api/v1/finance/", json=payload, headers=headers)
    assert no_id.status_code == 422

    assert await db_session.scalar(select(func.count()).select_from(FinanceAccount)) == 0

    confirmed = await confirm_agreement(client, headers, generated["agreement_id"])
    assert confirmed.status_code == 200, confirmed.text
    allowed = await client.post(
        "/api/v1/finance/",
        json={**payload, "agreement_id": generated["agreement_id"]},
        headers=headers,
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_terms_and_customer_mismatch_are_blocked(client, test_user):
    headers = auth(test_user)
    first = await _customer(client, headers, "Agreement Terms Customer", "9610000006")
    second = await _customer(client, headers, "Agreement Other Customer", "9610000007")
    agreement, payload = await generate_agreement(
        client, headers, first["id"], principal_amount="5000.00"
    )
    assert (await confirm_agreement(client, headers, agreement["agreement_id"])).status_code == 200

    changed_amount = await client.post(
        "/api/v1/finance/",
        json={
            **payload,
            "principal_amount": "6000.00",
            "agreement_id": agreement["agreement_id"],
        },
        headers=headers,
    )
    assert changed_amount.status_code == 400, changed_amount.text
    assert changed_amount.json()["error"]["code"] == "AGREEMENT_TERMS_MISMATCH"

    changed_customer = await client.post(
        "/api/v1/finance/",
        json={
            **payload,
            "customer_id": second["id"],
            "agreement_id": agreement["agreement_id"],
        },
        headers=headers,
    )
    assert changed_customer.status_code == 400, changed_customer.text
    assert changed_customer.json()["error"]["code"] == "AGREEMENT_CUSTOMER_MISMATCH"


@pytest.mark.asyncio
async def test_agreement_cannot_be_reused_and_multiple_accounts_allowed(
    client, test_user, db_session
):
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement Reuse Customer", "9610000008")
    account, agreement = await create_finance_account(client, headers, customer["id"])

    reused = await client.post(
        "/api/v1/finance/",
        json={**loan_payload(customer["id"]), "agreement_id": agreement["agreement_id"]},
        headers=headers,
    )
    assert reused.status_code == 400, reused.text
    assert reused.json()["error"]["code"] == "AGREEMENT_ALREADY_USED"
    assert await db_session.scalar(select(func.count()).select_from(FinanceAccount)) == 1

    second_account, second_agreement = await create_finance_account(
        client, headers, customer["id"], principal_amount="4500.00"
    )
    assert second_account["id"] != account["id"]
    assert second_agreement["agreement_id"] != agreement["agreement_id"]
    assert await db_session.scalar(select(func.count()).select_from(FinanceAccount)) == 2


@pytest.mark.asyncio
async def test_generation_never_activates_account_and_no_disbursement_field(
    client, test_user, test_engine, db_session
):
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement No Disbursement Customer", "9610000009")
    agreement, _ = await generate_agreement(client, headers, customer["id"])
    await print_agreement(client, headers, agreement["agreement_id"])
    assert await db_session.scalar(select(func.count()).select_from(FinanceAccount)) == 0

    confirm = await confirm_agreement(client, headers, agreement["agreement_id"])
    assert confirm.status_code == 200, confirm.text
    assert await db_session.scalar(select(func.count()).select_from(FinanceAccount)) == 0

    # Use the already-confirmed agreement explicitly to prove consumption.
    response = await client.post(
        "/api/v1/finance/",
        json={**loan_payload(customer["id"]), "agreement_id": agreement["agreement_id"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "ACTIVE"

    def _finance_columns(sync_conn):
        return {
            column["name"]
            for column in inspect(sync_conn).get_columns("finance_accounts")
        }

    async with test_engine.connect() as connection:
        columns = await connection.run_sync(_finance_columns)
    assert not [column for column in columns if "disburs" in column.lower()]
    assert "status" in columns

    stored = await db_session.get(FinanceAgreement, UUID(agreement["agreement_id"]))
    assert stored.agreement_status == "CONFIRMED"
    assert str(stored.finance_account_id) == response.json()["data"]["id"]


@pytest.mark.asyncio
async def test_agreement_consumption_is_audited(client, test_user, db_session):
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement Audit Customer", "9610000010")
    account, agreement = await create_finance_account(client, headers, customer["id"])

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "FINANCE_AGREEMENT_CONSUMED",
                AuditLog.entity_type == "FINANCE_AGREEMENT",
                AuditLog.entity_id == agreement["agreement_id"],
            )
        )
    ).scalar_one()
    assert audit.new_value["finance_account_id"] == account["id"]
    assert audit.new_value["agreement_id"] == agreement["agreement_id"]
    assert CONFIRMATION_TEXT.endswith("signed by the customer.")


@pytest.mark.asyncio
async def test_confirmed_agreement_can_still_be_printed(client, test_user):
    """Printing a signed agreement is allowed and never downgrades its status."""
    headers = auth(test_user)
    customer = await _customer(client, headers, "Agreement Reprint Customer", "9610000011")
    agreement, _ = await generate_agreement(client, headers, customer["id"])
    confirmed = await confirm_agreement(client, headers, agreement["agreement_id"])
    assert confirmed.status_code == 200, confirmed.text

    reprinted = await print_agreement(client, headers, agreement["agreement_id"])
    assert reprinted["status"] == "CONFIRMED"
    assert reprinted["print_count"] == 1
    assert reprinted["printed_at"]
    assert reprinted["agreement_html"] == agreement["agreement_html"]
