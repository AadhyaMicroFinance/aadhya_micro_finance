"""
Chitti Agreement repository.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chitti import ChittiAgreement
from app.repositories.base import BaseRepository


class ChittiAgreementRepository(BaseRepository[ChittiAgreement]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChittiAgreement, session)

    async def get_by_number(self, agreement_number: str) -> Optional[ChittiAgreement]:
        result = await self.session.execute(
            select(ChittiAgreement).where(
                ChittiAgreement.agreement_number == agreement_number
            )
        )
        return result.scalar_one_or_none()

    async def get_by_member_id(self, member_id: UUID) -> Optional[ChittiAgreement]:
        result = await self.session.execute(
            select(ChittiAgreement).where(
                ChittiAgreement.chitti_member_id == member_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_chitti_id(self, chitti_id: UUID) -> list[ChittiAgreement]:
        result = await self.session.execute(
            select(ChittiAgreement)
            .where(ChittiAgreement.chitti_id == chitti_id)
            .order_by(ChittiAgreement.created_at)
        )
        return list(result.scalars().all())

    async def count_by_chitti(self, chitti_id: UUID) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count()).select_from(ChittiAgreement).where(
                ChittiAgreement.chitti_id == chitti_id
            )
        )
        return result.scalar() or 0
