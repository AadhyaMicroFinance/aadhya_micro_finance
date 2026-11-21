"""Customer onboarding and search integrity regressions."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer


def _auth(test_user):
    return {"Authorization": f"Bearer {test_user['token']}"}


async def _create(client, headers, mobile, **extra):
    response = await client.post(
        "/api/v1/customers/",
        json={
            "full_name": "Integrity Customer",
            "mobile_number": mobile,
            "address": "Hyderabad",
            **extra,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_customer_mobile_validation_and_formatted_duplicate(
    client, test_user
):
    headers = _auth(test_user)

    invalid = await client.post(
        "/api/v1/customers/",
        json={"full_name": "Bad Mobile", "mobile_number": "abc12"},
        headers=headers,
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "CONFLICT"

    await _create(client, headers, "9876512345")
    duplicate = await client.post(
        "/api/v1/customers/",
        json={"full_name": "Formatted Duplicate", "mobile_number": "+91 98765-12345"},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_CUSTOMER_MOBILE"


@pytest.mark.asyncio
async def test_customer_search_paginates_with_true_total(
    client, test_user, db_session: AsyncSession
):
    headers = _auth(test_user)
    for index in range(60):
        db_session.add(Customer(
            customer_code=f"CUS-PAGE-{index:04d}",
            full_name=f"Searchable Customer {index:02d}",
            mobile_number=f"901000{index:04d}",
            status="ACTIVE",
        ))
    await db_session.flush()

    first = (await client.get(
        "/api/v1/customers/",
        params={"search": "Searchable Customer", "page": 1, "per_page": 25},
        headers=headers,
    )).json()
    third = (await client.get(
        "/api/v1/customers/",
        params={"search": "Searchable Customer", "page": 3, "per_page": 25},
        headers=headers,
    )).json()

    assert first["meta"]["total"] == 60
    assert len(first["data"]) == 25
    assert third["meta"]["total"] == 60
    assert len(third["data"]) == 10


@pytest.mark.asyncio
async def test_customer_update_can_clear_nullable_field(client, test_user):
    headers = _auth(test_user)
    customer = await _create(client, headers, "9876512399", email="clear-me@example.com")

    response = await client.put(
        f"/api/v1/customers/{customer['id']}",
        json={"email": None},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["email"] is None
