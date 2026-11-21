"""Administration screen APIs use the real audit/settings/notification tables."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.audit import AuditLog
from app.models.user import User
from app.models.whatsapp import WhatsAppMessageLog


async def _headers(db_session, role: str) -> dict:
    suffix = uuid4().hex[:8]
    user = User(
        id=uuid4(),
        username=f"admin-screen-{suffix}",
        email=f"admin-screen-{suffix}@test.com",
        password_hash="not-used",
        full_name="Admin Screen Tester",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = create_access_token(data={"sub": str(user.id), "role": role})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_settings_returns_effective_non_secret_values(client, db_session):
    response = await client.get(
        "/api/v1/admin/settings", headers=await _headers(db_session, "SUPER_ADMIN")
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["advance_payment_policy"] == "EXPLICIT_CREDIT_ONLY"
    assert data["notification_delivery_enabled"] is False
    assert isinstance(data["whatsapp_configured"], bool)
    assert "access_token" not in str(data).lower()
    assert "jwt_secret" not in str(data).lower()


@pytest.mark.asyncio
async def test_admin_without_audit_permission_cannot_read_audit(client, db_session):
    response = await client.get(
        "/api/v1/admin/audit", headers=await _headers(db_session, "ADMIN")
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_audit_list_returns_real_entries_and_filters(client, db_session):
    action = "ADMIN_SCREEN_TEST"
    db_session.add(
        AuditLog(
            action=action,
            entity_type="app_settings",
            new_value={"key": "business.timezone"},
        )
    )
    await db_session.flush()
    headers = await _headers(db_session, "SUPER_ADMIN")

    response = await client.get(
        "/api/v1/admin/audit", headers=headers, params={"action": action}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["action"] == action
    assert body["data"][0]["entity_type"] == "app_settings"
    assert body["data"][0]["actor"]

    other = await client.get(
        "/api/v1/admin/audit",
        headers=headers,
        params={"action": "NO_SUCH_AUDIT_ACTION"},
    )
    assert other.json()["meta"]["total"] == 0
    assert other.json()["data"] == []


@pytest.mark.asyncio
async def test_audit_rejects_inverted_date_range(client, db_session):
    response = await client.get(
        "/api/v1/admin/audit",
        headers=await _headers(db_session, "SUPER_ADMIN"),
        params={"date_from": "2026-02-02", "date_to": "2026-02-01"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_whatsapp_screen_reads_message_log(client, db_session, test_customer):
    db_session.add(
        WhatsAppMessageLog(
            customer_id=test_customer.id,
            phone_number=test_customer.mobile_number,
            template_name="PAYMENT_RECEIVED",
            status="SENT",
        )
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/admin/whatsapp", headers=await _headers(db_session, "ADMIN")
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["stats"]["sent_today"] >= 1
    assert data["stats"]["failed_today"] == 0
    assert any(
        message["template_name"] == "PAYMENT_RECEIVED"
        and message["customer_name"] == test_customer.full_name
        for message in data["messages"]
    )

    rows = (await db_session.execute(select(WhatsAppMessageLog))).scalars().all()
    assert len(rows) == 1
