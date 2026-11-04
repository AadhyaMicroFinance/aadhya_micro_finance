"""
Chitti service — orchestrates plans, instances, members, schedules, contributions, payouts.

All business logic lives here. API handlers should only call service methods.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chitti_rules import (
    validate_contribution_rules,
    validate_payout_rules,
)
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.repositories.chitti_repo import (
    ChittiContributionRepository,
    ChittiMemberRepository,
    ChittiPayoutRepository,
    ChittiPeriodScheduleRepository,
    ChittiPlanRepository,
    ChittiRepository,
    ChittiTransactionRepository,
)
from app.repositories.customer_repo import CustomerRepository
from app.services.chitti_calculation import ChittiCalculationEngine
from app.utils.codes import generate_chitti_code, generate_plan_code
from app.utils.timezone import today_ist


# Valid status transitions
VALID_TRANSITIONS = {
    "DRAFT": ["RUNNING", "CANCELLED"],
    "UPCOMING": ["RUNNING", "CANCELLED"],
    "RUNNING": ["PAUSED", "COMPLETED", "CANCELLED"],
    "PAUSED": ["RUNNING", "CANCELLED"],
    "COMPLETED": ["ARCHIVED"],
    "CANCELLED": [],
    "ARCHIVED": [],
}


class ChittiService:
    """Business logic for Chitti plans and instances."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.plan_repo = ChittiPlanRepository(session)
        self.chitti_repo = ChittiRepository(session)
        self.member_repo = ChittiMemberRepository(session)
        self.schedule_repo = ChittiPeriodScheduleRepository(session)
        self.contribution_repo = ChittiContributionRepository(session)
        self.payout_repo = ChittiPayoutRepository(session)
        self.txn_repo = ChittiTransactionRepository(session)
        self.customer_repo = CustomerRepository(session)

    # ===========================================================================
    # Plan CRUD
    # ===========================================================================

    async def create_plan(self, *, data: dict, created_by: Optional[UUID] = None) -> dict:
        """Create a new Chitti plan with validated rules."""
        # Validate rules
        validate_contribution_rules(data["contribution_rules"])
        validate_payout_rules(data["payout_rules"])

        plan_code = await generate_plan_code(self.session)

        plan = await self.plan_repo.create(
            plan_code=plan_code,
            name=data["name"],
            description=data.get("description"),
            chitti_type=data["chitti_type"],
            total_value=data["total_value"],
            currency=data.get("currency", "INR"),
            member_count=data["member_count"],
            frequency=data["frequency"],
            duration=data["duration"],
            contribution_rules=data["contribution_rules"],
            payout_rules=data["payout_rules"],
            fee_rules=data.get("fee_rules") or {},
            penalty_rules=data.get("penalty_rules") or {},
            is_active=True,
            created_by=created_by,
        )
        return self._plan_to_dict(plan)

    async def get_plan(self, plan_id: UUID) -> dict:
        plan = await self.plan_repo.get_by_id(plan_id)
        if not plan:
            raise NotFoundException("Chitti plan", plan_id)
        return self._plan_to_dict(plan)

    async def list_plans(
        self, page: int = 1, per_page: int = 25, active_only: bool = True
    ) -> tuple[list[dict], int]:
        skip = (page - 1) * per_page
        if active_only:
            plans, total = await self.plan_repo.list_active(skip=skip, limit=per_page)
        else:
            plans, total = await self.plan_repo.get_all(skip=skip, limit=per_page)
        return [self._plan_to_dict(p) for p in plans], total

    async def update_plan(self, plan_id: UUID, data: dict) -> dict:
        plan = await self.plan_repo.get_by_id(plan_id)
        if not plan:
            raise NotFoundException("Chitti plan", plan_id)

        # Validate updated rules if provided
        if "contribution_rules" in data:
            validate_contribution_rules(data["contribution_rules"])
        if "payout_rules" in data:
            validate_payout_rules(data["payout_rules"])

        plan = await self.plan_repo.update(plan, **data)
        return self._plan_to_dict(plan)

    async def duplicate_plan(self, plan_id: UUID, created_by: Optional[UUID] = None) -> dict:
        plan = await self.plan_repo.get_by_id(plan_id)
        if not plan:
            raise NotFoundException("Chitti plan", plan_id)

        new_code = await generate_plan_code(self.session)
        new_plan = await self.plan_repo.create(
            plan_code=new_code,
            name=f"{plan.name} (Copy)",
            description=plan.description,
            chitti_type=plan.chitti_type,
            total_value=plan.total_value,
            currency=plan.currency,
            member_count=plan.member_count,
            frequency=plan.frequency,
            duration=plan.duration,
            contribution_rules=plan.contribution_rules,
            payout_rules=plan.payout_rules,
            fee_rules=plan.fee_rules or {},
            penalty_rules=plan.penalty_rules or {},
            is_active=True,
            created_by=created_by,
        )
        return self._plan_to_dict(new_plan)

    async def deactivate_plan(self, plan_id: UUID) -> dict:
        plan = await self.plan_repo.get_by_id(plan_id)
        if not plan:
            raise NotFoundException("Chitti plan", plan_id)
        plan = await self.plan_repo.update(plan, is_active=False)
        return self._plan_to_dict(plan)

    async def activate_plan(self, plan_id: UUID) -> dict:
        plan = await self.plan_repo.get_by_id(plan_id)
        if not plan:
            raise NotFoundException("Chitti plan", plan_id)
        plan = await self.plan_repo.update(plan, is_active=True)
        return self._plan_to_dict(plan)

    # ===========================================================================
    # Chitti Preview
    # ===========================================================================

    async def preview_chitti(
        self,
        plan_id: UUID,
        start_date,
        member_count: Optional[int] = None,
    ) -> dict:
        """Generate a full preview of a chitti before creation."""
        plan = await self.plan_repo.get_by_id(plan_id)
        if not plan:
            raise NotFoundException("Chitti plan", plan_id)

        mc = member_count or plan.member_count
        snapshot = self._build_plan_snapshot(plan)
        engine = ChittiCalculationEngine(snapshot)
        preview = engine.preview_full_schedule(start_date, mc)

        return {
            **preview,
            "plan_name": plan.name,
            "chitti_type": plan.chitti_type,
            "frequency": plan.frequency,
            "duration": plan.duration,
            "member_count": mc,
            "total_value": plan.total_value,
        }

    # ===========================================================================
    # Chitti Instance CRUD
    # ===========================================================================

    async def create_chitti(self, *, data: dict, created_by: Optional[UUID] = None) -> dict:
        """Create a chitti instance from a plan. Creates plan snapshot + schedule + member slots."""
        plan = await self.plan_repo.get_by_id(UUID(data["plan_id"]))
        if not plan:
            raise NotFoundException("Chitti plan", data["plan_id"])
        if not plan.is_active:
            raise BadRequestException("Cannot create chitti from an inactive plan.")

        member_count = data.get("member_count") or plan.member_count
        if member_count < 1:
            raise BadRequestException("Member count must be at least 1.")

        # Build immutable plan snapshot
        snapshot = self._build_plan_snapshot(plan)
        engine = ChittiCalculationEngine(snapshot)

        # Calculate end date
        from app.services.chitti_calculation import FREQUENCY_DAYS
        from datetime import timedelta
        days_per_period = FREQUENCY_DAYS.get(plan.frequency, 30)
        total_days = days_per_period * plan.duration
        end_date = data["start_date"] + timedelta(days=total_days)

        chitti_code = await generate_chitti_code(self.session)

        chitti = await self.chitti_repo.create(
            chitti_code=chitti_code,
            plan_id=plan.id,
            plan_snapshot=snapshot,
            name=data["name"],
            branch=data.get("branch"),
            start_date=data["start_date"],
            end_date=end_date,
            member_count=member_count,
            total_value=plan.total_value,
            current_period=0,
            status="DRAFT",
            notes=data.get("notes"),
            created_by=created_by,
        )

        # Generate period schedule
        period_schedule = engine.generate_period_schedule(data["start_date"], member_count)
        for entry in period_schedule:
            await self.schedule_repo.create(chitti_id=chitti.id, **entry)

        return self._chitti_to_dict(chitti, plan_name=plan.name)

    async def get_chitti(self, chitti_id: UUID) -> dict:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)

        plan = await self.plan_repo.get_by_id(chitti.plan_id)
        plan_name = plan.name if plan else None
        return self._chitti_to_dict(chitti, plan_name=plan_name)

    async def list_chittis(
        self,
        page: int = 1,
        per_page: int = 25,
        status: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        skip = (page - 1) * per_page
        chittis, total = await self.chitti_repo.list_all_paginated(
            skip=skip, limit=per_page, status=status
        )
        # Get plan names
        plan_ids = {c.plan_id for c in chittis}
        plan_names = {}
        for pid in plan_ids:
            plan = await self.plan_repo.get_by_id(pid)
            if plan:
                plan_names[pid] = plan.name

        return [
            self._chitti_to_dict(c, plan_name=plan_names.get(c.plan_id))
            for c in chittis
        ], total

    async def update_chitti(self, chitti_id: UUID, data: dict) -> dict:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        if chitti.status != "DRAFT":
            raise BadRequestException("Only DRAFT chittis can be edited.")
        chitti = await self.chitti_repo.update(chitti, **data)
        plan = await self.plan_repo.get_by_id(chitti.plan_id)
        return self._chitti_to_dict(chitti, plan_name=plan.name if plan else None)

    async def change_status(self, chitti_id: UUID, new_status: str) -> dict:
        """Change chitti status with validation."""
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)

        allowed = VALID_TRANSITIONS.get(chitti.status, [])
        if new_status not in allowed:
            raise BadRequestException(
                f"Cannot transition from {chitti.status} to {new_status}. "
                f"Allowed: {', '.join(allowed) or 'none'}"
            )

        # Validate RUNNING requires members
        if new_status == "RUNNING":
            active_count = await self.member_repo.count_active(chitti.id)
            if active_count == 0:
                raise BadRequestException("Cannot start a chitti with no active members.")
            # Members enrolled through the agreement flow may predate contribution
            # generation; materialise their schedules so payments work from day one.
            await self._ensure_member_contributions(chitti)

        chitti = await self.chitti_repo.update(chitti, status=new_status)
        plan = await self.plan_repo.get_by_id(chitti.plan_id)
        return self._chitti_to_dict(chitti, plan_name=plan.name if plan else None)

    # ===========================================================================
    # Members
    # ===========================================================================

    async def add_member(
        self, chitti_id: UUID, *, customer_id: str, member_number: int,
        payout_order: Optional[int] = None,
    ) -> dict:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        if chitti.status not in ("DRAFT", "UPCOMING"):
            raise BadRequestException("Can only add members to DRAFT or UPCOMING chittis.")

        # Check customer exists
        customer = await self.customer_repo.get_by_id(UUID(customer_id))
        if not customer:
            raise NotFoundException("Customer", customer_id)

        # Check not duplicate
        existing = await self.member_repo.get_by_chitti_and_customer(chitti.id, UUID(customer_id))
        if existing:
            raise ConflictException("Customer is already a member of this chitti.")

        # Check member number not taken
        existing_num = await self.member_repo.get_by_chitti_and_member_number(
            chitti.id, member_number
        )
        if existing_num:
            raise ConflictException(f"Member number {member_number} is already taken.")

        member = await self.member_repo.create(
            chitti_id=chitti.id,
            customer_id=UUID(customer_id),
            member_number=member_number,
            payout_order=payout_order,
            status="ACTIVE",
        )

        # Generate contribution entries for this member
        snapshot = chitti.plan_snapshot
        engine = ChittiCalculationEngine(snapshot)
        contributions = engine.generate_member_contributions(
            member.id, member_number, chitti.start_date
        )
        for entry in contributions:
            entry["chitti_id"] = chitti.id
            await self.contribution_repo.create(**entry)

        return self._member_to_dict(member, customer)

    async def list_members(self, chitti_id: UUID) -> list[dict]:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)

        members = await self.member_repo.get_by_chitti_id(chitti.id)
        result = []
        for m in members:
            customer = await self.customer_repo.get_by_id(m.customer_id)
            # Calculate totals from contributions
            contributions = await self.contribution_repo.get_by_member_id(m.id)
            total_expected = sum(c.expected_amount for c in contributions)
            total_paid = sum(c.paid_amount for c in contributions)
            result.append(self._member_to_dict(
                m, customer,
                total_expected=total_expected,
                total_paid=total_paid,
            ))
        return result

    async def get_member_detail(self, chitti_id: UUID, member_id: UUID) -> dict:
        """Get full member detail including agreement info."""
        from app.repositories.agreement_repo import ChittiAgreementRepository
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)

        member = await self.member_repo.get_by_id(member_id)
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)

        customer = await self.customer_repo.get_by_id(member.customer_id)
        contributions = await self.contribution_repo.get_by_member_id(member.id)
        total_expected = sum(c.expected_amount for c in contributions)
        total_paid = sum(c.paid_amount for c in contributions)

        # Get agreement if exists
        agreement_repo = ChittiAgreementRepository(self.session)
        agreement = await agreement_repo.get_by_member_id(member.id)
        agreement_data = None
        if agreement:
            agreement_data = {
                "id": str(agreement.id),
                "agreement_number": agreement.agreement_number,
                "agreement_date": str(agreement.agreement_date),
                "agreement_status": agreement.agreement_status,
                "agreement_snapshot": agreement.agreement_snapshot,
                "generated_at": str(agreement.generated_at) if agreement.generated_at else None,
                "printed_at": str(agreement.printed_at) if agreement.printed_at else None,
                "print_count": agreement.print_count,
                "confirmed_at": str(agreement.confirmed_at) if agreement.confirmed_at else None,
                "cancelled_at": str(agreement.cancelled_at) if agreement.cancelled_at else None,
                "cancellation_reason": agreement.cancellation_reason,
            }

        return {
            "id": str(member.id),
            "chitti_id": str(member.chitti_id),
            "customer_id": str(member.customer_id),
            "customer_name": customer.full_name if customer else None,
            "customer_code": customer.customer_code if customer else None,
            "mobile_number": customer.mobile_number if customer else None,
            "member_number": member.member_number,
            "payout_order": member.payout_order,
            "status": member.status,
            "joined_at": str(member.joined_at),
            "total_expected_amount": float(total_expected),
            "total_paid_amount": float(total_paid),
            "outstanding_amount": float(total_expected - total_paid),
            "lifted": member.lifted,
            "lifted_at": str(member.lifted_at) if member.lifted_at else None,
            "lift_period": member.lift_period,
            "agreement": agreement_data,
        }

    async def remove_member(self, chitti_id: UUID, member_id: UUID) -> None:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        if chitti.status not in ("DRAFT", "UPCOMING"):
            raise BadRequestException("Can only remove members from DRAFT or UPCOMING chittis.")

        member = await self.member_repo.get_by_id(member_id)
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)

        await self.member_repo.delete(member)

    # ===========================================================================
    # Schedule & Contributions
    # ===========================================================================

    async def get_schedule(self, chitti_id: UUID) -> list[dict]:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)
        return [
            {
                "id": str(s.id),
                "chitti_id": str(s.chitti_id),
                "period_number": s.period_number,
                "due_date": str(s.due_date),
                "expected_collection": s.expected_collection,
                "actual_collection": s.actual_collection,
                "pending_collection": s.pending_collection,
                "expected_payout": s.expected_payout,
                "actual_payout": s.actual_payout,
                "status": s.status,
            }
            for s in schedules
        ]

    async def get_member_contributions(
        self, chitti_id: UUID, member_id: UUID
    ) -> list[dict]:
        contributions = await self.contribution_repo.get_by_member_id(member_id)
        return [
            {
                "id": str(c.id),
                "member_id": str(c.member_id),
                "period_number": c.period_number,
                "expected_amount": c.expected_amount,
                "paid_amount": c.paid_amount,
                "remaining_amount": c.remaining_amount,
                "status": c.status,
            }
            for c in contributions
        ]

    async def record_contribution(
        self,
        chitti_id: UUID,
        *,
        member_id: str,
        period_number: int,
        amount: Decimal,
        payment_method: str,
        payment_date,
        reference_number: Optional[str] = None,
        notes: Optional[str] = None,
        idempotency_key: str,
        created_by: Optional[UUID] = None,
    ) -> dict:
        """Record a contribution payment for a member."""
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        if chitti.status != "RUNNING":
            raise BadRequestException("Chitti is not in RUNNING status.")

        member = await self.member_repo.get_by_id(UUID(member_id))
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)

        # Idempotency — a retried request must never double-count a collection.
        existing_txn = await self.txn_repo.get_by_idempotency_key(idempotency_key)
        if existing_txn:
            prior = await self.contribution_repo.get_by_chitti_member_period(
                chitti.id, member.id, period_number
            )
            return {
                "contribution_id": str(prior.id) if prior else None,
                "paid_amount": prior.paid_amount if prior else Decimal("0"),
                "remaining_amount": prior.remaining_amount if prior else Decimal("0"),
                "status": prior.status if prior else "UNKNOWN",
                "duplicate": True,
            }

        contribution = await self.contribution_repo.get_by_chitti_member_period(
            chitti.id, member.id, period_number
        )
        if not contribution:
            raise NotFoundException("Contribution entry for this period")

        if contribution.status == "PAID":
            raise BadRequestException("This contribution is already fully paid.")

        # Update contribution
        new_paid = contribution.paid_amount + amount
        new_remaining = contribution.expected_amount - new_paid

        if new_remaining <= 0:
            new_status = "PAID"
            new_remaining = Decimal("0")
        elif new_paid > 0:
            new_status = "PARTIALLY_PAID"
        else:
            new_status = contribution.status

        contribution = await self.contribution_repo.update(
            contribution,
            paid_amount=new_paid,
            remaining_amount=new_remaining,
            status=new_status,
        )

        # Update period schedule aggregates
        period_schedule = await self.schedule_repo.get_by_period(chitti.id, period_number)
        if period_schedule:
            await self.schedule_repo.update(
                period_schedule,
                actual_collection=period_schedule.actual_collection + amount,
                pending_collection=max(
                    period_schedule.pending_collection - amount, Decimal("0")
                ),
            )

        # Record transaction with the business date and idempotency key.
        await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="CONTRIBUTION",
            member_id=member.id,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            period_number=period_number,
            notes=notes,
            payment_date=payment_date or today_ist(),
            idempotency_key=idempotency_key,
            created_by=created_by,
        )

        # Refresh member aggregates from the contribution rows (single source of truth).
        contributions = await self.contribution_repo.get_by_member_id(member.id)
        total_expected = sum((c.expected_amount for c in contributions), Decimal("0"))
        total_paid = sum((c.paid_amount for c in contributions), Decimal("0"))
        await self.member_repo.update(
            member,
            total_expected_amount=total_expected,
            total_paid_amount=total_paid,
            outstanding_amount=max(total_expected - total_paid, Decimal("0")),
        )

        return {
            "contribution_id": str(contribution.id),
            "paid_amount": contribution.paid_amount,
            "remaining_amount": contribution.remaining_amount,
            "status": contribution.status,
            "duplicate": False,
        }

    # ===========================================================================
    # Payouts
    # ===========================================================================

    async def list_payouts(self, chitti_id: UUID) -> list[dict]:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        payouts = await self.payout_repo.get_by_chitti_id(chitti.id)
        return [
            {
                "id": str(p.id),
                "chitti_id": str(p.chitti_id),
                "member_id": str(p.member_id),
                "period_number": p.period_number,
                "gross_payout": p.gross_payout,
                "discount_amount": p.discount_amount,
                "fee_amount": p.fee_amount,
                "net_payout": p.net_payout,
                "payout_method": p.payout_method,
                "paid_at": str(p.paid_at) if p.paid_at else None,
                "status": p.status,
            }
            for p in payouts
        ]

    async def record_payout(
        self,
        chitti_id: UUID,
        *,
        member_id: str,
        period_number: int,
        gross_payout: Decimal,
        discount_amount: Decimal = Decimal("0"),
        fee_amount: Decimal = Decimal("0"),
        net_payout: Decimal,
        payout_method: str,
        created_by: Optional[UUID] = None,
    ) -> dict:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)

        member = await self.member_repo.get_by_id(UUID(member_id))
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)

        from app.utils.timezone import now_ist

        payout = await self.payout_repo.create(
            chitti_id=chitti.id,
            member_id=member.id,
            period_number=period_number,
            gross_payout=gross_payout,
            discount_amount=discount_amount,
            fee_amount=fee_amount,
            net_payout=net_payout,
            payout_method=payout_method,
            paid_at=now_ist(),
            status="PAID",
        )

        # Update period schedule
        period_schedule = await self.schedule_repo.get_by_period(chitti.id, period_number)
        if period_schedule:
            await self.schedule_repo.update(
                period_schedule,
                actual_payout=period_schedule.actual_payout + net_payout,
            )

        # Record transaction
        await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="PAYOUT",
            member_id=member.id,
            amount=net_payout,
            payment_method=payout_method,
            period_number=period_number,
            created_by=created_by,
        )

        return {
            "id": str(payout.id),
            "gross_payout": payout.gross_payout,
            "net_payout": payout.net_payout,
            "status": payout.status,
        }

    # ===========================================================================
    # Dashboard & Summary
    # ===========================================================================

    async def get_dashboard(self) -> list[dict]:
        """Get summary for all active chittis (DRAFT, UPCOMING, RUNNING, PAUSED)."""
        from sqlalchemy import select
        from app.models.chitti import Chitti as ChittiModel
        result_chittis = []
        for status in ["RUNNING", "DRAFT", "UPCOMING", "PAUSED"]:
            chittis, _ = await self.chitti_repo.list_by_status(status, limit=100)
            result_chittis.extend(chittis)
        result = []
        for chitti in result_chittis:
            plan = await self.plan_repo.get_by_id(chitti.plan_id)
            active_members = await self.member_repo.count_active(chitti.id)
            schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)
            total_expected = sum(s.expected_collection for s in schedules)
            total_actual = sum(s.actual_collection for s in schedules)
            total_pending = sum(s.pending_collection for s in schedules)

            next_period = next(
                (s for s in schedules if s.status in ("UPCOMING", "ACTIVE")), None
            )

            result.append({
                "id": str(chitti.id),
                "chitti_code": chitti.chitti_code,
                "name": chitti.name,
                "plan_name": plan.name if plan else None,
                "status": chitti.status,
                "member_count": active_members,
                "current_period": chitti.current_period,
                "total_periods": chitti.plan_snapshot.get("duration", 0),
                "total_value": chitti.total_value,
                "expected_collection": total_expected,
                "actual_collection": total_actual,
                "pending_collection": total_pending,
                "next_due_date": str(next_period.due_date) if next_period else None,
                "start_date": str(chitti.start_date),
                "end_date": str(chitti.end_date),
            })
        return result

    async def get_summary(self, chitti_id: UUID) -> dict:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)

        plan = await self.plan_repo.get_by_id(chitti.plan_id)
        active_members = await self.member_repo.count_active(chitti.id)
        schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)
        payouts = await self.payout_repo.get_by_chitti_id(chitti.id)

        total_expected = sum(s.expected_collection for s in schedules)
        total_actual = sum(s.actual_collection for s in schedules)
        total_pending = sum(s.pending_collection for s in schedules)
        total_payouts = sum(p.net_payout for p in payouts if p.status == "PAID")

        next_period = next(
            (s for s in schedules if s.status in ("UPCOMING", "ACTIVE")), None
        )
        next_payout = next(
            (p for p in payouts if p.status == "PENDING"), None
        )

        return {
            "chitti_id": str(chitti.id),
            "chitti_name": chitti.name,
            "status": chitti.status,
            "member_count": chitti.member_count,
            "active_members": active_members,
            "current_period": chitti.current_period,
            "total_periods": chitti.plan_snapshot.get("duration", 0),
            "total_value": chitti.total_value,
            "expected_collection": total_expected,
            "actual_collection": total_actual,
            "pending_collection": total_pending,
            "total_payouts": total_payouts,
            "outstanding": total_expected - total_actual,
            "next_due_date": str(next_period.due_date) if next_period else None,
            "next_payout_date": str(next_payout.paid_at) if next_payout else None,
        }

    # ===========================================================================
    # Helpers
    # ===========================================================================

    async def _ensure_member_contributions(self, chitti) -> None:
        """Generate missing per-member schedules and refresh member totals."""
        members = await self.member_repo.get_active_members(chitti.id)
        engine = ChittiCalculationEngine(chitti.plan_snapshot or {})
        for member in members:
            contributions = await self.contribution_repo.get_by_member_id(member.id)
            if not contributions:
                entries = engine.generate_member_contributions(
                    member.id,
                    member.member_number,
                    chitti.start_date,
                    member_lift_period=member.payout_order or member.member_number,
                )
                for entry in entries:
                    entry["chitti_id"] = chitti.id
                    await self.contribution_repo.create(**entry)
                contributions = await self.contribution_repo.get_by_member_id(member.id)

            total_expected = sum(
                (c.expected_amount for c in contributions), Decimal("0")
            )
            total_paid = sum((c.paid_amount for c in contributions), Decimal("0"))
            await self.member_repo.update(
                member,
                total_expected_amount=total_expected,
                total_paid_amount=total_paid,
                outstanding_amount=max(total_expected - total_paid, Decimal("0")),
            )

    def _build_plan_snapshot(self, plan: "ChittiPlan") -> dict:
        """Build an immutable snapshot of plan rules."""
        return {
            "plan_id": str(plan.id),
            "plan_code": plan.plan_code,
            "name": plan.name,
            "chitti_type": plan.chitti_type,
            "total_value": float(plan.total_value),
            "currency": plan.currency,
            "member_count": plan.member_count,
            "frequency": plan.frequency,
            "duration": plan.duration,
            "contribution_rules": plan.contribution_rules,
            "payout_rules": plan.payout_rules,
            "fee_rules": plan.fee_rules or {},
            "penalty_rules": plan.penalty_rules or {},
        }

    def _plan_to_dict(self, plan) -> dict:
        return {
            "id": str(plan.id),
            "plan_code": plan.plan_code,
            "name": plan.name,
            "description": plan.description,
            "chitti_type": plan.chitti_type,
            "total_value": plan.total_value,
            "currency": plan.currency,
            "member_count": plan.member_count,
            "frequency": plan.frequency,
            "duration": plan.duration,
            "contribution_rules": plan.contribution_rules,
            "payout_rules": plan.payout_rules,
            "fee_rules": plan.fee_rules,
            "penalty_rules": plan.penalty_rules,
            "is_active": plan.is_active,
            "created_by": str(plan.created_by) if plan.created_by else None,
            "created_at": str(plan.created_at),
            "updated_at": str(plan.updated_at),
        }

    def _chitti_to_dict(self, chitti, plan_name: Optional[str] = None) -> dict:
        return {
            "id": str(chitti.id),
            "chitti_code": chitti.chitti_code,
            "plan_id": str(chitti.plan_id),
            "plan_name": plan_name,
            "name": chitti.name,
            "branch": chitti.branch,
            "start_date": str(chitti.start_date),
            "end_date": str(chitti.end_date),
            "member_count": chitti.member_count,
            "total_value": chitti.total_value,
            "current_period": chitti.current_period,
            "status": chitti.status,
            "notes": chitti.notes,
            "plan_snapshot": chitti.plan_snapshot,
            "created_by": str(chitti.created_by) if chitti.created_by else None,
            "created_at": str(chitti.created_at),
            "updated_at": str(chitti.updated_at),
        }

    def _member_to_dict(self, member, customer=None, total_expected=Decimal("0"), total_paid=Decimal("0")) -> dict:
        return {
            "id": str(member.id),
            "chitti_id": str(member.chitti_id),
            "customer_id": str(member.customer_id),
            "customer_name": customer.full_name if customer else None,
            "customer_code": customer.customer_code if customer else None,
            "mobile_number": customer.mobile_number if customer else None,
            "member_number": member.member_number,
            "payout_order": member.payout_order,
            "status": member.status,
            "joined_at": str(member.joined_at),
            "total_expected": total_expected,
            "total_paid": total_paid,
            "outstanding": total_expected - total_paid,
        }
