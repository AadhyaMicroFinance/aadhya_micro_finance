"""
Audit logging service.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit_repo import AuditLogRepository


class AuditService:
    """Centralized audit logging."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.audit_repo = AuditLogRepository(session)

    async def log(
        self,
        *,
        user_id: Optional[UUID] = None,
        action: str,
        entity_type: str,
        entity_id: Optional[UUID] = None,
        previous_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Log an audit entry."""
        await self.audit_repo.log(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=previous_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def get_entity_history(
        self, entity_type: str, entity_id: UUID
    ) -> list[dict]:
        """Get audit history for a specific entity."""
        logs = await self.audit_repo.get_by_entity(entity_type, entity_id)
        return [
            {
                "id": str(log.id),
                "user_id": str(log.user_id) if log.user_id else None,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": str(log.entity_id) if log.entity_id else None,
                "previous_value": log.previous_value,
                "new_value": log.new_value,
                "created_at": str(log.created_at),
            }
            for log in logs
        ]
