"""Small helpers for Finance tests that must create a signed agreement first."""

from datetime import date

CONFIRMATION_TEXT = "I confirm that the agreement has been signed by the customer."


def auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


def loan_payload(customer_id: str, **overrides) -> dict:
    """Default loan fields shared by agreement generation and account creation."""
    payload = {
        "customer_id": customer_id,
        "principal_amount": "3000.00",
        "interest_rate": "0",
        "interest_type": "FLAT",
        "fees": "0",
        "frequency": "MONTHLY",
        "start_date": date.today().isoformat(),
        "first_due_date": date.today().isoformat(),
        "number_of_installments": 1,
    }
    payload.update(overrides)
    return payload


async def generate_agreement(client, headers, customer_id: str, **overrides):
    payload = loan_payload(customer_id, **overrides)
    response = await client.post(
        "/api/v1/finance/agreements/generate", json=payload, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"], payload


async def print_agreement(client, headers, agreement_id: str):
    response = await client.post(
        f"/api/v1/finance/agreements/{agreement_id}/print", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def confirm_agreement(
    client, headers, agreement_id: str, confirmation_text: str = CONFIRMATION_TEXT
):
    return await client.post(
        f"/api/v1/finance/agreements/{agreement_id}/confirm",
        json={"confirmation_text": confirmation_text},
        headers=headers,
    )


async def prepare_agreement(client, headers, customer_id: str, *, confirm: bool = True, **overrides):
    """Generate → print → (optionally) confirm an agreement for a customer."""
    agreement, payload = await generate_agreement(client, headers, customer_id, **overrides)
    await print_agreement(client, headers, agreement["agreement_id"])
    if confirm:
        response = await confirm_agreement(client, headers, agreement["agreement_id"])
        assert response.status_code == 200, response.text
    return agreement, payload


async def create_finance_account(client, headers, customer_id: str, **overrides):
    """Create a signed agreement, then create the Finance account from it."""
    agreement, payload = await prepare_agreement(client, headers, customer_id, **overrides)
    response = await client.post(
        "/api/v1/finance/",
        json={**payload, "agreement_id": agreement["agreement_id"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"], agreement
