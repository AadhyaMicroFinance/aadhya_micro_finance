"""
Customer repository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    """Customer-specific database operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Customer, session)

    async def get_by_code(self, customer_code: str) -> Optional[Customer]:
        """Find customer by customer code."""
        result = await self.session.execute(
            select(Customer).where(Customer.customer_code == customer_code)
        )
        return result.scalar_one_or_none()

    async def get_by_mobile(self, mobile_number: str) -> Optional[Customer]:
        """Find customer by normalized phone digits to catch formatted duplicates."""
        digits = "".join(ch for ch in mobile_number if ch.isdigit())
        result = await self.session.execute(
            select(Customer).where(
                func.regexp_replace(Customer.mobile_number, r"\D", "", "g") == digits
            )
        )
        return result.scalar_one_or_none()

    async def get_by_mobile_excluding(self, mobile_number: str, customer_id: UUID) -> Optional[Customer]:
        digits = "".join(ch for ch in mobile_number if ch.isdigit())
        result = await self.session.execute(select(Customer).where(
            Customer.id != customer_id,
            func.regexp_replace(Customer.mobile_number, r"\D", "", "g") == digits,
        ))
        return result.scalar_one_or_none()

    async def get_by_id(self, id) -> Optional[Customer]:
        """Get customer by ID."""
        if isinstance(id, str):
            id = UUID(id)
        result = await self.session.execute(
            select(Customer).where(Customer.id == id)
        )
        return result.scalar_one_or_none()

    async def search(self, query: str) -> list[Customer]:
        """Search customers by name, code, or mobile number."""
        search = f"%{query}%"
        result = await self.session.execute(
            select(Customer).where(
                (Customer.full_name.ilike(search))
                | (Customer.customer_code.ilike(search))
                | (Customer.mobile_number.ilike(search))
            ).limit(50)
        )
        return list(result.scalars().all())
