"""
User management service.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import hash_password
from app.repositories.user_repo import UserRepository


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

        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        }

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

    async def update_user(
        self,
        user_id: UUID,
        *,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
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
            await self.user_repo.update(user, **updates)

        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        }

    async def delete_user(self, user_id: UUID) -> None:
        """Soft-delete a user by deactivating."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", user_id)
        await self.user_repo.update(user, is_active=False)
