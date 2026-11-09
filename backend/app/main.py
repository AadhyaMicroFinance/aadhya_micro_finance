"""
FastAPI application factory.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.exceptions import AppException
from app.core.middleware import RequestLoggingMiddleware, RequestIDMiddleware
from app.api.v1.router import api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    yield
    # Shutdown


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    # Exception handlers
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        error: dict = {
            "code": exc.error_code,
            "message": exc.message,
        }
        # Machine-readable context (blocked prerequisites, duplicate enrollment
        # details, ...) so the UI can explain the failure instead of showing
        # a bare HTTP status.
        if exc.details is not None:
            error["details"] = exc.details
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": error},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                },
            },
        )

    # Register API router
    app.include_router(api_v1_router, prefix="/api/v1")

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
