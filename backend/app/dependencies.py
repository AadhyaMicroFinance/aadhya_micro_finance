"""
Dependency injection for FastAPI routes.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import decode_token
from app.core.exceptions import UnauthorizedException
from app.models.user import User
from app.repositories.user_repo import UserRepository

security_scheme = HTTPBearer()

# Database session dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from the JWT token."""
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise UnauthorizedException("Invalid or expired token.")

    token_type = payload.get("type")
    if token_type != "access":
        raise UnauthorizedException("Invalid token type.")

    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedException("Invalid token payload.")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise UnauthorizedException("User not found.")
    if not user.is_active:
        raise UnauthorizedException("User account is deactivated.")

    return user


# Commonly used dependency types
CurrentUser = Annotated[User, Depends(get_current_user)]
