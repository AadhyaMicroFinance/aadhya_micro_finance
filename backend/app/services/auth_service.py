"""
Authentication service.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.repositories.user_repo import UserRepository


class AuthService:
    """Handles authentication flows."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def login(self, username: str, password: str) -> dict:
        """Authenticate user and return tokens."""
        user = await self.user_repo.get_by_username(username)
        if user is None:
            raise UnauthorizedException("Invalid username or password.")

        if not verify_password(password, user.password_hash):
            raise UnauthorizedException("Invalid username or password.")

        if not user.is_active:
            raise UnauthorizedException("Your account has been deactivated.")

        access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
        refresh_token = create_refresh_token(data={"sub": str(user.id), "role": user.role})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def refresh_token(self, refresh_token: str) -> dict:
        """Validate refresh token and issue new token pair."""
        payload = decode_token(refresh_token)
        if payload is None:
            raise UnauthorizedException("Invalid or expired refresh token.")

        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid token type.")

        user_id = payload.get("sub")
        user = await self.user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedException("User not found or deactivated.")

        new_access = create_access_token(data={"sub": str(user.id), "role": user.role})
        new_refresh = create_refresh_token(data={"sub": str(user.id), "role": user.role})

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }

    async def get_me(self, user_id: UUID) -> dict:
        """Get current user information with permissions."""
        from app.core.permissions import ROLE_PERMISSIONS

        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise UnauthorizedException("User not found.")

        permissions = [
            p.value for p in ROLE_PERMISSIONS.get(user.role, [])
        ]

        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "permissions": permissions,
        }
