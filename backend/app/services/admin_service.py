"""Read models for the administration screens.

These queries only read existing audit, settings and notification tables. They
never change business rules, financial allocations, or historical records.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import BadRequestException
from app.models.audit import AuditLog
from app.models.customer import Customer
from app.models.settings import AppSettings
from app.models.user import User
from app.models.whatsapp import WhatsAppMessageLog
from app.utils.timezone import BUSINESS_TZ


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


class AdminService:
    """Read-only administration data for Settings, Audit and WhatsApp pages."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def settings_payload(self) -> dict:
        settings = get_settings()
        rows = (
            await self.session.execute(
                select(AppSettings).order_by(AppSettings.key.asc())
            )
        ).scalars().all()
        saved = [
            {
                "key": row.key,
                "value": row.value,
                "description": row.description,
                "updated_at": _iso(row.updated_at),
            }
            for row in rows
        ]
        return {
            "business_timezone": settings.APP_TIMEZONE,
            # This is an approved financial rule, not an operator preference.
            # Credits are always applied explicitly and never auto-allocated.
            "advance_payment_policy": "EXPLICIT_CREDIT_ONLY",
            "notification_delivery_enabled": False,
            "whatsapp_configured": bool(
                settings.WHATSAPP_PHONE_NUMBER_ID and settings.WHATSAPP_ACCESS_TOKEN
            ),
            "saved_settings": saved,
        }

    async def audit_logs(
        self,
        *,
        date_from: Optional[date],
        date_to: Optional[date],
        action: Optional[str],
        entity_type: Optional[str],
        page: int,
        per_page: int,
    ) -> dict:
        if date_from and date_to and date_from > date_to:
            raise BadRequestException("'date_from' cannot be after 'date_to'.")

        filters = []
        if date_from:
            start = datetime.combine(date_from, time.min, tzinfo=BUSINESS_TZ)
            filters.append(AuditLog.created_at >= start)
        if date_to:
            end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ)
            filters.append(AuditLog.created_at < end)
        if action:
            filters.append(AuditLog.action == action)
        if entity_type:
            filters.append(AuditLog.entity_type == entity_type)

        total = (
            await self.session.execute(
                select(func.count()).select_from(AuditLog).where(*filters)
            )
        ).scalar_one()
        rows = (
            await self.session.execute(
                select(AuditLog, User.username)
                .outerjoin(User, User.id == AuditLog.user_id)
                .where(*filters)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        ).all()
        return {
            "items": [
                {
                    "id": str(log.id),
                    "created_at": _iso(log.created_at),
                    "actor": username or "System",
                    "action": log.action,
                    "entity_type": log.entity_type,
                    "entity_id": str(log.entity_id) if log.entity_id else None,
                    "previous_value": log.previous_value,
                    "new_value": log.new_value,
                }
                for log, username in rows
            ],
            "total": int(total),
            "page": page,
            "per_page": per_page,
            "total_pages": (int(total) + per_page - 1) // per_page,
        }

    async def whatsapp_payload(self, *, limit: int) -> dict:
        today = datetime.now(BUSINESS_TZ).date()
        day_start = datetime.combine(today, time.min, tzinfo=BUSINESS_TZ)
        day_end = day_start + timedelta(days=1)
        counts = dict(
            (
                await self.session.execute(
                    select(WhatsAppMessageLog.status, func.count())
                    .where(
                        WhatsAppMessageLog.created_at >= day_start,
                        WhatsAppMessageLog.created_at < day_end,
                    )
                    .group_by(WhatsAppMessageLog.status)
                )
            ).all()
        )
        sent_today = sum(
            int(counts.get(status, 0))
            for status in ("SENT", "DELIVERED", "READ")
        )
        failed_today = int(counts.get("FAILED", 0))
        attempted_today = sent_today + failed_today + int(counts.get("QUEUED", 0))
        settings = get_settings()
        rows = (
            await self.session.execute(
                select(WhatsAppMessageLog, Customer.full_name)
                .outerjoin(Customer, Customer.id == WhatsAppMessageLog.customer_id)
                .order_by(WhatsAppMessageLog.created_at.desc())
                .limit(limit)
            )
        ).all()
        return {
            "configured": bool(
                settings.WHATSAPP_PHONE_NUMBER_ID and settings.WHATSAPP_ACCESS_TOKEN
            ),
            "stats": {
                "sent_today": sent_today,
                "failed_today": failed_today,
                "delivery_rate": round(sent_today * 100 / attempted_today, 1)
                if attempted_today
                else None,
            },
            "messages": [
                {
                    "id": str(log.id),
                    "customer_name": customer_name or "Unknown customer",
                    "phone_number": log.phone_number,
                    "template_name": log.template_name,
                    "status": log.status,
                    "error_message": log.error_message,
                    "created_at": _iso(log.created_at),
                }
                for log, customer_name in rows
            ],
        }
