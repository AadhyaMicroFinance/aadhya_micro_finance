"""
Customer API tests.
"""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_create_customer(client, test_user):
    """Create a new customer."""
    response = await client.post(
        "/api/v1/customers/",
        json={
            "full_name": "Ravi Kumar",
            "mobile_number": "9876543211",
            "address": "Vijayawada, AP",
        },
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["customer_code"].startswith("CUS-")
    assert data["data"]["full_name"] == "Ravi Kumar"


@pytest.mark.asyncio
async def test_list_customers(client, test_user, test_customer):
    """List customers."""
    response = await client.get(
        "/api/v1/customers/",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_get_customer(client, test_user, test_customer):
    """Get a specific customer."""
    response = await client.get(
        f"/api/v1/customers/{test_customer.id}",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["full_name"] == "Sravan Kumar"


@pytest.mark.asyncio
async def test_duplicate_mobile_fails(client, test_user, test_customer):
    """Creating a customer with duplicate mobile fails."""
    response = await client.post(
        "/api/v1/customers/",
        json={
            "full_name": "Duplicate Mobile",
            "mobile_number": "9876543210",  # Same as test_customer
        },
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_customer(client, test_user, test_customer):
    """Update customer info."""
    response = await client.put(
        f"/api/v1/customers/{test_customer.id}",
        json={"full_name": "Sravan Kumar Updated"},
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["full_name"] == "Sravan Kumar Updated"


@pytest.mark.asyncio
async def test_get_customer_ledger(client, test_user, test_customer):
    """Get customer ledger."""
    response = await client.get(
        f"/api/v1/customers/{test_customer.id}/ledger",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "customer" in data["data"]
    assert "finance_accounts" in data["data"]
    assert "payment_history" in data["data"]
