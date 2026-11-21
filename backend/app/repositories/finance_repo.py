"""
Finance repository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.finance import FinanceAccount, FinanceAgreement, FinanceSchedule
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
        """Get finance account by ID with schedules and customer summary."""
        if isinstance(id, str):
            id = UUID(id)
        result = await self.session.execute(
            select(FinanceAccount)
            .options(
                selectinload(FinanceAccount.schedules),
                selectinload(FinanceAccount.customer),
            )
            .where(FinanceAccount.id == id)
        )
        return result.scalar_one_or_none()

    async def list_with_customer(
        self,
        *,
        skip: int = 0,
        limit: int = 25,
        filters: Optional[dict] = None,
        search: Optional[str] = None,
        agreement_status: Optional[str] = None,
    ) -> tuple[list[tuple[FinanceAccount, Customer]], int]:
        """List accounts with their customer row for display without N+1 lookups."""
        query = select(FinanceAccount, Customer).join(
            Customer, Customer.id == FinanceAccount.customer_id
        )
        count_query = select(func.count()).select_from(FinanceAccount).join(
            Customer, Customer.id == FinanceAccount.customer_id
        )

        if search:
            pattern = f"%{search.strip()}%"
            condition = or_(
                Customer.full_name.ilike(pattern),
                Customer.mobile_number.ilike(pattern),
                FinanceAccount.account_number.ilike(pattern),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        if agreement_status:
            linked = exists(
                select(FinanceAgreement.id).where(
                    FinanceAgreement.finance_account_id == FinanceAccount.id
                )
            )
            condition = (
                ~linked
                if agreement_status == "NONE"
                else exists(
                    select(FinanceAgreement.id).where(
                        FinanceAgreement.finance_account_id == FinanceAccount.id,
                        FinanceAgreement.agreement_status == agreement_status,
                    )
                )
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        for key, value in (filters or {}).items():
            if value is not None and hasattr(FinanceAccount, key):
                condition = getattr(FinanceAccount, key) == value
                query = query.where(condition)
                count_query = count_query.where(condition)

        total = (await self.session.execute(count_query)).scalar_one()
        rows = (
            await self.session.execute(
                query
                .order_by(FinanceAccount.created_at.desc(), FinanceAccount.id.desc())
                .offset(skip)
                .limit(limit)
            )
        ).all()
        return [(row[0], row[1]) for row in rows], int(total)

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
                FinanceSchedule.status.in_(["DUE", "UPCOMING", "PARTIALLY_PAID"]),
            )
            .order_by(FinanceSchedule.due_date)
            .limit(1)
        )
        return result.scalar_one_or_none()
