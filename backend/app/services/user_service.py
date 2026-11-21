"""
User management service.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import hash_password
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService


class UserService:
    """User CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        full_name: str,
        role: str,
        actor_id: Optional[UUID] = None,
    ) -> dict:
        """Create a new user."""
        # Check uniqueness
        existing = await self.user_repo.get_by_username(username)
        if existing:
            raise ConflictException("Username already exists.")

        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise ConflictException("Email already exists.")

        user = await self.user_repo.create(
            username=username,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
        )

        payload = {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        }
        await AuditService(self.session).log(
            user_id=actor_id,
            action="USER_CREATED",
            entity_type="USER",
            entity_id=user.id,
            new_value=payload,
        )
        return payload

    async def get_user(self, user_id: UUID) -> dict:
        """Get a user by ID."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", user_id)
        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        }

    async def list_users(
        self,
        page: int = 1,
        per_page: int = 25,
        role: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """List users with pagination."""
        filters = {}
        if role:
            filters["role"] = role

        skip = (page - 1) * per_page
        users, total = await self.user_repo.get_all(
            skip=skip, limit=per_page, filters=filters
        )

        items = [
            {
                "id": str(u.id),
                "username": u.username,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "is_active": u.is_active,
            }
            for u in users
        ]
        return items, total

    async def _assert_active_super_admin_remains(
        self,
        user,
        updates: dict,
    ) -> None:
        """Prevent the final active SUPER_ADMIN from being demoted/disabled."""
        loses_admin = (
            user.role == "SUPER_ADMIN"
            and (
                updates.get("role") not in (None, "SUPER_ADMIN")
                or updates.get("is_active") is False
            )
        )
        if not loses_admin:
            return
        _, total = await self.user_repo.get_all(
            filters={"role": "SUPER_ADMIN", "is_active": True},
            limit=1,
        )
        if total <= 1:
            raise ConflictException(
                "At least one active SUPER_ADMIN must remain.",
                error_code="LAST_SUPER_ADMIN",
            )

    async def update_user(
        self,
        user_id: UUID,
        *,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        actor_id: Optional[UUID] = None,
    ) -> dict:
        """Update a user."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", user_id)

        updates = {}
        if email is not None:
            existing = await self.user_repo.get_by_email(email)
            if existing and existing.id != user_id:
                raise ConflictException("Email already in use.")
            updates["email"] = email
        if full_name is not None:
            updates["full_name"] = full_name
        if role is not None:
            updates["role"] = role
        if is_active is not None:
            updates["is_active"] = is_active

        if updates:
            await self._assert_active_super_admin_remains(user, updates)
            previous = {
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
            }
            await self.user_repo.update(user, **updates)
            await AuditService(self.session).log(
                user_id=actor_id,
                action="USER_UPDATED",
                entity_type="USER",
                entity_id=user.id,
                previous_value=previous,
                new_value={
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "is_active": user.is_active,
                },
            )

        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        }

    async def delete_user(
        self,
        user_id: UUID,
        *,
        actor_id: Optional[UUID] = None,
    ) -> None:
        """Soft-delete a user by deactivating."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", user_id)
        await self._assert_active_super_admin_remains(
            user, {"is_active": False}
        )
        previous = {"is_active": user.is_active}
        await self.user_repo.update(user, is_active=False)
        await AuditService(self.session).log(
            user_id=actor_id,
            action="USER_DEACTIVATED",
            entity_type="USER",
            entity_id=user.id,
            previous_value=previous,
            new_value={"is_active": user.is_active},
        )
