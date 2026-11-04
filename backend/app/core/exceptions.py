"""
Custom application exceptions.
All API errors should use these for consistent error responses.
"""

from typing import Any, Optional


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int = 400,
        details: Optional[Any] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found."""

    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} with identifier '{identifier}' not found.",
            error_code="NOT_FOUND",
            status_code=404,
        )


class BadRequestException(AppException):
    """Invalid request / bad input."""

    def __init__(self, message: str, error_code: str = "BAD_REQUEST"):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=400,
        )


class UnauthorizedException(AppException):
    """Authentication required or invalid credentials."""

    def __init__(self, message: str = "Invalid credentials."):
        super().__init__(
            message=message,
            error_code="UNAUTHORIZED",
            status_code=401,
        )


class ForbiddenException(AppException):
    """Insufficient permissions."""

    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(
            message=message,
            error_code="FORBIDDEN",
            status_code=403,
        )


class ConflictException(AppException):
    """Resource already exists or conflicting state."""

    def __init__(self, message: str, error_code: str = "CONFLICT"):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=409,
        )


class PaymentExceedsBalanceException(AppException):
    """Payment amount exceeds outstanding balance."""

    def __init__(self, outstanding: float, attempted: float):
        super().__init__(
            message=f"Payment amount ₹{attempted:,.2f} exceeds outstanding balance ₹{outstanding:,.2f}.",
            error_code="PAYMENT_EXCEEDS_BALANCE",
            status_code=400,
        )


class DuplicatePaymentException(AppException):
    """Duplicate payment detected via idempotency key."""

    def __init__(self):
        super().__init__(
            message="This payment has already been processed.",
            error_code="DUPLICATE_PAYMENT",
            status_code=409,
        )


class TransactionFailedException(AppException):
    """Database transaction could not be committed."""

    def __init__(self, message: str = "Transaction failed. Please try again."):
        super().__init__(
            message=message,
            error_code="TRANSACTION_FAILED",
            status_code=500,
        )
