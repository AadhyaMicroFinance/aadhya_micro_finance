"""
Auth API endpoints.
"""

from fastapi import APIRouter

from app.dependencies import CurrentUser, DBSession
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, MeResponse
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/login", response_model=ApiResponse)
async def login(body: LoginRequest, db: DBSession):
    """Authenticate user and return access + refresh tokens."""
    service = AuthService(db)
    tokens = await service.login(body.username, body.password)
    return ApiResponse(data=tokens)


@router.post("/refresh", response_model=ApiResponse)
async def refresh_token(body: RefreshRequest, db: DBSession):
    """Refresh access token using refresh token."""
    service = AuthService(db)
    tokens = await service.refresh_token(body.refresh_token)
    return ApiResponse(data=tokens)


@router.post("/logout", response_model=ApiResponse)
async def logout(current_user: CurrentUser):
    """Logout (client should discard tokens)."""
    return ApiResponse(data={"message": "Logged out successfully."})


@router.get("/me", response_model=ApiResponse)
async def get_me(current_user: CurrentUser, db: DBSession):
    """Get current user info and permissions."""
    service = AuthService(db)
    user_data = await service.get_me(current_user.id)
    return ApiResponse(data=user_data)
