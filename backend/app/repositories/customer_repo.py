"""
Customer repository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
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
        """Find customer by mobile number."""
        result = await self.session.execute(
            select(Customer).where(Customer.mobile_number == mobile_number)
        )
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
