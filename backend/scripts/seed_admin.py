"""
Create the first SUPER_ADMIN account if it does not exist.

Idempotent: running it again never changes an existing password.
Driven by ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_FULL_NAME.
"""

import asyncio
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.database import async_session_factory
from app.models.user import User


async def main() -> int:
    username = (os.getenv("ADMIN_USERNAME") or "admin").strip()
    password = os.getenv("ADMIN_PASSWORD") or ""
    email = (os.getenv("ADMIN_EMAIL") or f"{username}@example.com").strip()
    full_name = (os.getenv("ADMIN_FULL_NAME") or "System Administrator").strip()

    if not password:
        print("ADMIN_PASSWORD is not set - skipping admin bootstrap.")
        return 0
    if len(password) < 8:
        print("ADMIN_PASSWORD must be at least 8 characters.", file=sys.stderr)
        return 1

    async with async_session_factory() as session:
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()

        if existing is not None:
            print(f"Admin '{username}' already exists - password left unchanged.")
            return 0

        session.add(
            User(
                username=username,
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role="SUPER_ADMIN",
                is_active=True,
            )
        )
        await session.commit()
        print(f"Created SUPER_ADMIN '{username}'.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
