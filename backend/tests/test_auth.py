"""
Authentication API tests.
"""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_login_success(client, test_user):
    """Successful login returns tokens."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "testpass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]


@pytest.mark.asyncio
async def test_login_wrong_password(client, test_user):
    """Login with wrong password fails."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "wrongpass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    """Login with nonexistent user fails."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nouser", "password": "nopass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client, test_user):
    """Get current user info with valid token."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["username"] == "testadmin"
    assert data["data"]["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_get_me_no_token(client):
    """Get me without token fails."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token(client, test_user):
    """Refresh token returns new tokens."""
    # First login to get a valid refresh token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "testpass123"},
    )
    refresh_token = login_response.json()["data"]["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data["data"]
