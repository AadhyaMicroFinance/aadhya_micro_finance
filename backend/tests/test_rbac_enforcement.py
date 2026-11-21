"""Permission dependencies must actually execute for protected routes."""

import pytest


ADMIN_ONLY_TOKEN_HEADER = "Authorization"


@pytest.mark.asyncio
async def test_admin_cannot_read_users(client, test_user):
    """ADMIN lacks users:read; the old bare checker default silently bypassed it."""
    response = await client.get(
        "/api/v1/users/",
        headers={ADMIN_ONLY_TOKEN_HEADER: f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_cannot_reverse_chitti_receipt(client, test_user):
    """ADMIN lacks payments:reverse on the Chitti receipt-reversal route."""
    response = await client.post(
        "/api/v1/chitti/00000000-0000-0000-0000-000000000001/transactions/"
        "00000000-0000-0000-0000-000000000002/reverse",
        json={"reversal_reason": "permission check"},
        headers={ADMIN_ONLY_TOKEN_HEADER: f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_can_read_customers(client, test_user):
    """Permitted routes keep working once the dependency is active."""
    response = await client.get(
        "/api/v1/customers/",
        headers={ADMIN_ONLY_TOKEN_HEADER: f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200, response.text
