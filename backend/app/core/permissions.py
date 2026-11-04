"""
Role-Based Access Control (RBAC) permissions.

Permissions follow the format: resource:action
Examples: customers:read, finance:create, payments:reverse

All permission checks happen on the backend.
Frontend hides/shows UI elements but never trusts them for security.
"""

from enum import Enum
from typing import Optional

from fastapi import Depends

from app.core.exceptions import ForbiddenException
from app.models.user import User


class Permission(str, Enum):
    # Users
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    USERS_DELETE = "users:delete"

    # Roles
    ROLES_READ = "roles:read"
    ROLES_WRITE = "roles:write"

    # Customers
    CUSTOMERS_READ = "customers:read"
    CUSTOMERS_WRITE = "customers:write"

    # Finance
    FINANCE_READ = "finance:read"
    FINANCE_CREATE = "finance:create"
    FINANCE_WRITE = "finance:write"

    # Chitti
    CHITTI_READ = "chitti:read"
    CHITTI_CREATE = "chitti:create"
    CHITTI_WRITE = "chitti:write"

    # Payments
    PAYMENTS_READ = "payments:read"
    PAYMENTS_CREATE = "payments:create"
    PAYMENTS_REVERSE = "payments:reverse"

    # Reports
    REPORTS_READ = "reports:read"

    # Settings
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"

    # Audit
    AUDIT_READ = "audit:read"

    # WhatsApp
    WHATSAPP_READ = "whatsapp:read"
    WHATSAPP_WRITE = "whatsapp:write"


# Default permissions per role
ROLE_PERMISSIONS: dict[str, list[Permission]] = {
    "SUPER_ADMIN": [
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.USERS_DELETE,
        Permission.ROLES_READ,
        Permission.ROLES_WRITE,
        Permission.CUSTOMERS_READ,
        Permission.CUSTOMERS_WRITE,
        Permission.FINANCE_READ,
        Permission.FINANCE_CREATE,
        Permission.FINANCE_WRITE,
        Permission.CHITTI_READ,
        Permission.CHITTI_CREATE,
        Permission.CHITTI_WRITE,
        Permission.PAYMENTS_READ,
        Permission.PAYMENTS_CREATE,
        Permission.PAYMENTS_REVERSE,
        Permission.REPORTS_READ,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
        Permission.AUDIT_READ,
        Permission.WHATSAPP_READ,
        Permission.WHATSAPP_WRITE,
    ],
    "ADMIN": [
        Permission.CUSTOMERS_READ,
        Permission.CUSTOMERS_WRITE,
        Permission.FINANCE_READ,
        Permission.FINANCE_CREATE,
        Permission.FINANCE_WRITE,
        Permission.CHITTI_READ,
        Permission.CHITTI_CREATE,
        Permission.CHITTI_WRITE,
        Permission.PAYMENTS_READ,
        Permission.PAYMENTS_CREATE,
        Permission.REPORTS_READ,
        Permission.WHATSAPP_READ,
    ],
    "STAFF": [
        Permission.CUSTOMERS_READ,
        Permission.CUSTOMERS_WRITE,
        Permission.FINANCE_READ,
        Permission.CHITTI_READ,
        Permission.PAYMENTS_READ,
        Permission.PAYMENTS_CREATE,
    ],
    "COLLECTOR": [
        Permission.CUSTOMERS_READ,
        Permission.FINANCE_READ,
        Permission.CHITTI_READ,
        Permission.PAYMENTS_READ,
        Permission.PAYMENTS_CREATE,
    ],
}


def get_user_permissions(user: User) -> set[str]:
    """Get all effective permissions for a user based on their role."""
    role = user.role
    if isinstance(role, str):
        return set(ROLE_PERMISSIONS.get(role, []))
    return set()


def require_permissions(*required: Permission):
    """
    Dependency that checks if the current user has all required permissions.

    Usage:
        @router.get("/customers", dependencies=[Depends(require_permissions(Permission.CUSTOMERS_READ))])
        async def list_customers(): ...
    """
    from app.dependencies import get_current_user

    def permission_checker(current_user: User = Depends(get_current_user)):
        user_permissions = get_user_permissions(current_user)
        for perm in required:
            if perm.value not in user_permissions:
                raise ForbiddenException(
                    f"Required permission: {perm.value}"
                )
        return current_user

    return permission_checker
