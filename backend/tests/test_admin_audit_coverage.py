"""Privileged user/customer changes must be auditable and self-protecting."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.audit import AuditLog
from app.models.user import User


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_customer_and_user_creation_write_audit_entries(
    client, db_session
):
    actor = User(
        id=uuid4(),
        username=f"audit-actor-{uuid4().hex[:8]}",
        email=f"audit-actor-{uuid4().hex[:8]}@test.com",
        password_hash="not-used",
        full_name="Audit Actor",
        role="SUPER_ADMIN",
        is_active=True,
    )
    db_session.add(actor)
    await db_session.flush()
    headers = _auth(
        create_access_token(data={"sub": str(actor.id), "role": "SUPER_ADMIN"})
    )

    customer = await client.post(
        "/api/v1/customers/",
        json={"full_name": "Audited Customer", "mobile_number": "9876598765"},
        headers=headers,
    )
    assert customer.status_code == 200, customer.text
    user = await client.post(
        "/api/v1/users/",
        json={
            "username": "audited-user",
            "email": "audited-user@test.com",
            "password": "StrongPass123!",
            "full_name": "Audited User",
            "role": "STAFF",
        },
        headers=headers,
    )
    assert user.status_code == 200, user.text

    actions = {
        row.action: row
        for row in (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action.in_(("CUSTOMER_CREATED", "USER_CREATED"))
                )
            )
        ).scalars()
    }
    assert set(actions) == {"CUSTOMER_CREATED", "USER_CREATED"}
    assert actions["CUSTOMER_CREATED"].user_id == actor.id
    assert actions["USER_CREATED"].user_id == actor.id


@pytest.mark.asyncio
async def test_last_super_admin_cannot_demote_or_deactivate_self(
    client, db_session
):
    admin = User(
        id=uuid4(),
        username=f"last-super-{uuid4().hex[:8]}",
        email=f"last-super-{uuid4().hex[:8]}@test.com",
        password_hash="not-used",
        full_name="Last Super Admin",
        role="SUPER_ADMIN",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()
    headers = _auth(create_access_token(data={"sub": str(admin.id), "role": "SUPER_ADMIN"}))
    user_id = str(admin.id)

    demote = await client.put(
        f"/api/v1/users/{user_id}", json={"role": "STAFF"}, headers=headers
    )
    assert demote.status_code == 409, demote.text
    assert demote.json()["error"]["code"] == "LAST_SUPER_ADMIN"

    deactivate = await client.delete(
        f"/api/v1/users/{user_id}", headers=headers
    )
    assert deactivate.status_code == 409, deactivate.text
    assert deactivate.json()["error"]["code"] == "LAST_SUPER_ADMIN"
