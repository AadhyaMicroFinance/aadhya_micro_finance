"""
Finance repository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.finance import FinanceAccount, FinanceSchedule
from app.repositories.base import BaseRepository


class FinanceAccountRepository(BaseRepository[FinanceAccount]):
    """Finance account database operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(FinanceAccount, session)

    async def get_by_account_number(self, account_number: str) -> Optional[FinanceAccount]:
        """Find finance account by account number."""
        result = await self.session.execute(
            select(FinanceAccount).where(
                FinanceAccount.account_number == account_number
            )
        )
        return result.scalar_one_or_none()

    async def get_by_customer_id(self, customer_id: UUID) -> list[FinanceAccount]:
        """Get all finance accounts for a customer."""
        result = await self.session.execute(
            select(FinanceAccount).where(
                FinanceAccount.customer_id == customer_id
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, id) -> Optional[FinanceAccount]:
        """Get finance account by ID with schedules."""
        if isinstance(id, str):
            id = UUID(id)
        result = await self.session.execute(
            select(FinanceAccount)
            .options(selectinload(FinanceAccount.schedules))
            .where(FinanceAccount.id == id)
        )
        return result.scalar_one_or_none()

    async def count_active(self) -> int:
        """Count active finance accounts."""
        return await self.count(filters={"status": "ACTIVE"})


class FinanceScheduleRepository(BaseRepository[FinanceSchedule]):
    """Finance schedule database operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(FinanceSchedule, session)

    async def get_by_finance_account_id(self, finance_account_id: UUID) -> list[FinanceSchedule]:
        """Get all schedules for a finance account, ordered by installment number."""
        result = await self.session.execute(
            select(FinanceSchedule)
            .where(FinanceSchedule.finance_account_id == finance_account_id)
            .order_by(FinanceSchedule.installment_number)
        )
        return list(result.scalars().all())

    async def get_upcoming_due(self, finance_account_id: UUID) -> Optional[FinanceSchedule]:
        """Get the next due schedule for an account."""
        result = await self.session.execute(
            select(FinanceSchedule)
            .where(
                FinanceSchedule.finance_account_id == finance_account_id,
                FinanceSchedule.status.in_(["DUE", "UPCOMING"]),
            )
            .order_by(FinanceSchedule.due_date)
            .limit(1)
        )
        return result.scalar_one_or_none()
