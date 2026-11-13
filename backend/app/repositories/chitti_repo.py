"""
Chitti repositories — Plan, Instance, Member, Schedule, Contribution, Payout, Transaction.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chitti import (
    Chitti,
    ChittiMember,
    ChittiMemberContribution,
    ChittiPayout,
    ChittiPeriodSchedule,
    ChittiPlan,
    ChittiTransaction,
)
from app.repositories.base import BaseRepository

# A member stops counting as enrolled only when the enrollment ends. This must
# match AnalyticsService._load_members(), which excludes the same three states.
ENROLLED_EXCLUDED_STATUSES = ("CANCELLED", "REJECTED", "LEFT")


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


class ChittiPlanRepository(BaseRepository[ChittiPlan]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChittiPlan, session)

    async def get_by_plan_code(self, plan_code: str) -> Optional[ChittiPlan]:
        result = await self.session.execute(
            select(ChittiPlan).where(ChittiPlan.plan_code == plan_code)
        )
        return result.scalar_one_or_none()

    async def list_active(self, skip: int = 0, limit: int = 25) -> tuple[list[ChittiPlan], int]:
        return await self.get_all(skip=skip, limit=limit, filters={"is_active": True})

    async def count_active(self) -> int:
        return await self.count(filters={"is_active": True})


# ---------------------------------------------------------------------------
# Chitti (Instance)
# ---------------------------------------------------------------------------


class ChittiRepository(BaseRepository[Chitti]):
    def __init__(self, session: AsyncSession):
        super().__init__(Chitti, session)

    async def get_by_chitti_code(self, chitti_code: str) -> Optional[Chitti]:
        result = await self.session.execute(
            select(Chitti).where(Chitti.chitti_code == chitti_code)
        )
        return result.scalar_one_or_none()

    async def list_by_status(
        self, status: str, skip: int = 0, limit: int = 25
    ) -> tuple[list[Chitti], int]:
        return await self.get_all(skip=skip, limit=limit, filters={"status": status})

    async def list_all_paginated(
        self, skip: int = 0, limit: int = 25, status: Optional[str] = None
    ) -> tuple[list[Chitti], int]:
        filters = {}
        if status:
            filters["status"] = status
        return await self.get_all(skip=skip, limit=limit, filters=filters)

    async def count_by_status(self, status: str) -> int:
        return await self.count(filters={"status": status})

    async def get_running_chittis(self) -> list[Chitti]:
        result = await self.session.execute(
            select(Chitti).where(Chitti.status == "RUNNING").order_by(Chitti.start_date)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Member
# ---------------------------------------------------------------------------


class ChittiMemberRepository(BaseRepository[ChittiMember]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChittiMember, session)

    async def get_by_chitti_id(self, chitti_id: UUID) -> list[ChittiMember]:
        result = await self.session.execute(
            select(ChittiMember)
            .where(ChittiMember.chitti_id == chitti_id)
            .order_by(ChittiMember.member_number)
        )
        return list(result.scalars().all())

    async def get_active_members(self, chitti_id: UUID) -> list[ChittiMember]:
        result = await self.session.execute(
            select(ChittiMember)
            .where(ChittiMember.chitti_id == chitti_id, ChittiMember.status == "ACTIVE")
            .order_by(ChittiMember.member_number)
        )
        return list(result.scalars().all())

    async def count_active(self, chitti_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(ChittiMember).where(
                ChittiMember.chitti_id == chitti_id,
                ChittiMember.status == "ACTIVE",
            )
        )
        return result.scalar() or 0

    async def count_enrolled(self, chitti_id: UUID) -> int:
        """Members that still hold a place in the chitti.

        Members move through PENDING_AGREEMENT -> AGREEMENT_GENERATED ->
        AGREEMENT_PRINTED -> ACTIVE, so only rows that were explicitly
        cancelled or rejected stop counting as enrolled. Counting ACTIVE only
        made dashboards report 0 members while the Members tab listed them all.
        """
        result = await self.session.execute(
            select(func.count()).select_from(ChittiMember).where(
                ChittiMember.chitti_id == chitti_id,
                ChittiMember.status.notin_(ENROLLED_EXCLUDED_STATUSES),
            )
        )
        return result.scalar() or 0

    async def count_enrolled_by_chitti(
        self, chitti_ids: list[UUID]
    ) -> dict[UUID, int]:
        """Enrolled-member counts for many chittis in one query (list screens)."""
        if not chitti_ids:
            return {}
        result = await self.session.execute(
            select(ChittiMember.chitti_id, func.count())
            .where(
                ChittiMember.chitti_id.in_(chitti_ids),
                ChittiMember.status.notin_(ENROLLED_EXCLUDED_STATUSES),
            )
            .group_by(ChittiMember.chitti_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_pending_agreements(self, chitti_id: UUID) -> int:
        """Enrolled members that have not completed the agreement workflow."""
        result = await self.session.execute(
            select(func.count()).select_from(ChittiMember).where(
                ChittiMember.chitti_id == chitti_id,
                ChittiMember.status.in_(
                    ["PENDING_AGREEMENT", "AGREEMENT_GENERATED", "AGREEMENT_PRINTED"]
                ),
            )
        )
        return result.scalar() or 0

    async def get_by_chitti_and_customer(
        self, chitti_id: UUID, customer_id: UUID
    ) -> Optional[ChittiMember]:
        result = await self.session.execute(
            select(ChittiMember).where(
                ChittiMember.chitti_id == chitti_id,
                ChittiMember.customer_id == customer_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_customer_id(self, customer_id: UUID) -> list[ChittiMember]:
        result = await self.session.execute(
            select(ChittiMember)
            .where(ChittiMember.customer_id == customer_id)
            .order_by(ChittiMember.joined_at)
        )
        return list(result.scalars().all())

    async def get_by_chitti_and_member_number(
        self, chitti_id: UUID, member_number: int
    ) -> Optional[ChittiMember]:
        result = await self.session.execute(
            select(ChittiMember).where(
                ChittiMember.chitti_id == chitti_id,
                ChittiMember.member_number == member_number,
            )
        )
        return result.scalar_one_or_none()

    async def max_member_number(self, chitti_id: UUID) -> int:
        result = await self.session.execute(
            select(func.max(ChittiMember.member_number)).where(
                ChittiMember.chitti_id == chitti_id
            )
        )
        return result.scalar() or 0


# ---------------------------------------------------------------------------
# Period Schedule
# ---------------------------------------------------------------------------


class ChittiPeriodScheduleRepository(BaseRepository[ChittiPeriodSchedule]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChittiPeriodSchedule, session)

    async def get_by_chitti_id(self, chitti_id: UUID) -> list[ChittiPeriodSchedule]:
        result = await self.session.execute(
            select(ChittiPeriodSchedule)
            .where(ChittiPeriodSchedule.chitti_id == chitti_id)
            .order_by(ChittiPeriodSchedule.period_number)
        )
        return list(result.scalars().all())

    async def get_by_period(
        self, chitti_id: UUID, period_number: int
    ) -> Optional[ChittiPeriodSchedule]:
        result = await self.session.execute(
            select(ChittiPeriodSchedule).where(
                ChittiPeriodSchedule.chitti_id == chitti_id,
                ChittiPeriodSchedule.period_number == period_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_next_upcoming(self, chitti_id: UUID) -> Optional[ChittiPeriodSchedule]:
        result = await self.session.execute(
            select(ChittiPeriodSchedule)
            .where(
                ChittiPeriodSchedule.chitti_id == chitti_id,
                ChittiPeriodSchedule.status.in_(["UPCOMING", "ACTIVE"]),
            )
            .order_by(ChittiPeriodSchedule.period_number)
            .limit(1)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Member Contribution
# ---------------------------------------------------------------------------


class ChittiContributionRepository(BaseRepository[ChittiMemberContribution]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChittiMemberContribution, session)

    async def get_by_chitti_id(self, chitti_id: UUID) -> list[ChittiMemberContribution]:
        result = await self.session.execute(
            select(ChittiMemberContribution)
            .where(ChittiMemberContribution.chitti_id == chitti_id)
            .order_by(ChittiMemberContribution.period_number)
        )
        return list(result.scalars().all())

    async def get_by_member_id(self, member_id: UUID) -> list[ChittiMemberContribution]:
        result = await self.session.execute(
            select(ChittiMemberContribution)
            .where(ChittiMemberContribution.member_id == member_id)
            .order_by(ChittiMemberContribution.period_number)
        )
        return list(result.scalars().all())

    async def get_by_chitti_and_period(
        self, chitti_id: UUID, period_number: int
    ) -> list[ChittiMemberContribution]:
        result = await self.session.execute(
            select(ChittiMemberContribution)
            .where(
                ChittiMemberContribution.chitti_id == chitti_id,
                ChittiMemberContribution.period_number == period_number,
            )
            .order_by(ChittiMemberContribution.member_id)
        )
        return list(result.scalars().all())

    async def get_by_chitti_member_period(
        self, chitti_id: UUID, member_id: UUID, period_number: int
    ) -> Optional[ChittiMemberContribution]:
        result = await self.session.execute(
            select(ChittiMemberContribution).where(
                ChittiMemberContribution.chitti_id == chitti_id,
                ChittiMemberContribution.member_id == member_id,
                ChittiMemberContribution.period_number == period_number,
            )
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Payout
# ---------------------------------------------------------------------------


class ChittiPayoutRepository(BaseRepository[ChittiPayout]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChittiPayout, session)

    async def get_by_chitti_id(self, chitti_id: UUID) -> list[ChittiPayout]:
        result = await self.session.execute(
            select(ChittiPayout)
            .where(ChittiPayout.chitti_id == chitti_id)
            .order_by(ChittiPayout.period_number)
        )
        return list(result.scalars().all())

    async def get_by_chitti_and_period(
        self, chitti_id: UUID, period_number: int
    ) -> list[ChittiPayout]:
        result = await self.session.execute(
            select(ChittiPayout)
            .where(
                ChittiPayout.chitti_id == chitti_id,
                ChittiPayout.period_number == period_number,
            )
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Transaction Ledger
# ---------------------------------------------------------------------------


class ChittiTransactionRepository(BaseRepository[ChittiTransaction]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChittiTransaction, session)

    async def get_by_chitti_id(self, chitti_id: UUID) -> list[ChittiTransaction]:
        result = await self.session.execute(
            select(ChittiTransaction)
            .where(ChittiTransaction.chitti_id == chitti_id)
            .order_by(ChittiTransaction.created_at)
        )
        return list(result.scalars().all())

    async def get_by_member_id(self, member_id: UUID) -> list[ChittiTransaction]:
        result = await self.session.execute(
            select(ChittiTransaction)
            .where(ChittiTransaction.member_id == member_id)
            .order_by(ChittiTransaction.payment_date, ChittiTransaction.created_at)
        )
        return list(result.scalars().all())

    async def get_by_idempotency_key(self, key: str) -> Optional[ChittiTransaction]:
        result = await self.session.execute(
            select(ChittiTransaction).where(
                ChittiTransaction.idempotency_key == key
            )
        )
        return result.scalar_one_or_none()
