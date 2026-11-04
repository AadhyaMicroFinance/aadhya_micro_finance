"""
Payment transaction repository.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import PaymentTransaction
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[PaymentTransaction]):
    """Payment transaction database operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(PaymentTransaction, session)

    async def get_by_transaction_id(self, transaction_id: str) -> Optional[PaymentTransaction]:
        result = await self.session.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.transaction_id == transaction_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Optional[PaymentTransaction]:
        result = await self.session.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.idempotency_key == key
            )
        )
        return result.scalar_one_or_none()

    async def get_by_customer_id(self, customer_id: UUID) -> list[PaymentTransaction]:
        result = await self.session.execute(
            select(PaymentTransaction)
            .where(PaymentTransaction.customer_id == customer_id)
            .order_by(PaymentTransaction.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_finance_account_id(self, finance_account_id: UUID) -> list[PaymentTransaction]:
        result = await self.session.execute(
            select(PaymentTransaction)
            .where(PaymentTransaction.finance_account_id == finance_account_id)
            .order_by(PaymentTransaction.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_date(
        self,
        payment_date: date,
        collector_id: Optional[UUID] = None,
    ) -> list[PaymentTransaction]:
        """Get all payments for a specific date."""
        query = select(PaymentTransaction).where(
            PaymentTransaction.payment_date == payment_date,
            PaymentTransaction.status == "COMPLETED",
        )
        if collector_id:
            query = query.where(PaymentTransaction.collected_by == collector_id)
        query = query.order_by(PaymentTransaction.created_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_total_collected_by_date(
        self,
        payment_date: date,
    ) -> dict:
        """Get collection totals for a date."""
        result = await self.session.execute(
            select(
                func.sum(PaymentTransaction.amount),
                func.count(PaymentTransaction.id),
            )
            .where(
                PaymentTransaction.payment_date == payment_date,
                PaymentTransaction.status == "COMPLETED",
            )
        )
        row = result.one()
        return {
            "total": row[0] or 0,
            "count": row[1] or 0,
        }

    async def get_total_by_date_and_method(self, payment_date: date) -> dict:
        """Get collection totals grouped by payment method."""
        result = await self.session.execute(
            select(
                PaymentTransaction.payment_method,
                func.sum(PaymentTransaction.amount),
                func.count(PaymentTransaction.id),
            )
            .where(
                PaymentTransaction.payment_date == payment_date,
                PaymentTransaction.status == "COMPLETED",
            )
            .group_by(PaymentTransaction.payment_method)
        )
        return {
            row[0]: {"amount": row[1] or 0, "count": row[2] or 0}
            for row in result.all()
        }
