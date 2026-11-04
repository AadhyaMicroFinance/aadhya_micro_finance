"""
Application configuration using pydantic-settings.
All secrets loaded from environment variables.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "Finance & Chitti Management System"
    APP_VERSION: str = "1.0.0"
    APP_TIMEZONE: str = "Asia/Kolkata"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_chitti"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/finance_chitti"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # WhatsApp Business Cloud API
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: Optional[str] = None
    WHATSAPP_API_VERSION: str = "v18.0"
    WHATSAPP_VERIFY_TOKEN: Optional[str] = None

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Account code prefixes
    CUSTOMER_CODE_PREFIX: str = "CUS"
    FINANCE_CODE_PREFIX: str = "FIN"
    CHITTI_CODE_PREFIX: str = "CHIT"
    PAYMENT_CODE_PREFIX: str = "PAY"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
