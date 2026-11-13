"""
Chitti service — orchestrates plans, instances, members, schedules, contributions, payouts.

All business logic lives here. API handlers should only call service methods.
"""

import logging
from decimal import Decimal, InvalidOperation
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

logger = logging.getLogger("app.chitti")

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
        enrolled = await self.member_repo.count_enrolled(chitti.id)
        return self._chitti_to_dict(
            chitti, plan_name=plan_name, enrolled_members=enrolled
        )

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

        enrolled_map = await self.member_repo.count_enrolled_by_chitti(
            [c.id for c in chittis]
        )
        return [
            self._chitti_to_dict(
                c,
                plan_name=plan_names.get(c.plan_id),
                enrolled_members=enrolled_map.get(c.id, 0),
            )
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

    async def change_status(
        self, chitti_id: UUID, new_status: str, created_by: Optional[UUID] = None
    ) -> dict:
        """Change chitti status with validation."""
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)

        allowed = VALID_TRANSITIONS.get(chitti.status, [])
        if new_status not in allowed:
            raise BadRequestException(
                f"Cannot transition from {chitti.status} to {new_status}. "
                f"Allowed: {', '.join(allowed) or 'none'}",
                error_code="INVALID_STATUS_TRANSITION",
                details={
                    "current_status": chitti.status,
                    "requested_status": new_status,
                    "allowed": allowed,
                },
            )

        previous_status = chitti.status

        if new_status == "RUNNING":
            # Activation is evaluated once, in activation_status(), so the
            # API, the UI and this transition can never disagree about
            # whether a chitti is startable. Resuming a PAUSED chitti is not a
            # start, so the "only DRAFT can start" rule is not applied there.
            activation = await self.activation_status(
                chitti,
                require_startable_status=chitti.status in ("DRAFT", "UPCOMING"),
            )
            if not activation["can_activate"]:
                reasons = " ".join(b["message"] for b in activation["blockers"])
                raise BadRequestException(
                    f"This chitti cannot be started yet. {reasons}",
                    error_code="ACTIVATION_BLOCKED",
                    details=activation,
                )
            # Members enrolled through the agreement flow may predate contribution
            # generation; materialise their schedules so payments work from day one.
            await self._ensure_member_contributions(chitti)
            # Period aggregates are projected from the plan capacity when a
            # chitti is created, but only the members who actually signed
            # contribute. Rebuild them from the authoritative per-member ledger
            # so schedules, analytics and the dashboard cannot disagree.
            await self._sync_period_schedules_from_contributions(chitti)

        chitti = await self.chitti_repo.update(chitti, status=new_status)

        from app.services.audit_service import AuditService
        await AuditService(self.session).log(
            user_id=created_by,
            action=f"CHITTI_STATUS_{new_status}",
            entity_type="chitti",
            entity_id=chitti.id,
            previous_value={"status": previous_status},
            new_value={"status": new_status},
        )

        plan = await self.plan_repo.get_by_id(chitti.plan_id)
        return self._chitti_to_dict(chitti, plan_name=plan.name if plan else None)

    # ===========================================================================
    # Activation prerequisites
    # ===========================================================================

    async def evaluate_activation(self, chitti_id: UUID) -> dict:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        return await self.activation_status(
            chitti, require_startable_status=chitti.status in ("DRAFT", "UPCOMING")
        )

    async def activation_status(
        self, chitti, *, require_startable_status: bool = True
    ) -> dict:
        """Single source of truth for whether a chitti can be started.

        Rules: members must exist, every enrolled member's agreement must be
        confirmed (i.e. physically signed), and a period schedule must exist.
        The "all agreements signed" rule is the business owner's decision: a
        chitti must never start while any enrolled member's agreement is
        unsigned, because that member cannot be held to the terms.
        """
        enrolled = await self.member_repo.count_enrolled(chitti.id)
        active = await self.member_repo.count_active(chitti.id)
        pending_agreements = await self.member_repo.count_pending_agreements(chitti.id)
        schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)

        blockers: list[dict] = []
        warnings: list[dict] = []

        if require_startable_status and chitti.status not in ("DRAFT", "UPCOMING"):
            blockers.append({
                "code": "NOT_STARTABLE",
                "message": f"Chitti is already {chitti.status}; only DRAFT chittis can be started.",
            })
        if enrolled == 0:
            blockers.append({
                "code": "NO_MEMBERS",
                "message": "No members are enrolled in this chitti.",
            })
        elif active == 0:
            blockers.append({
                "code": "NO_ACTIVE_MEMBERS",
                "message": (
                    f"{pending_agreements} member(s) still have an incomplete agreement. "
                    "Generate, print and confirm each agreement to activate them before starting."
                ),
            })
        elif pending_agreements > 0:
            blockers.append({
                "code": "AGREEMENTS_PENDING",
                "message": (
                    f"{pending_agreements} enrolled member(s) have not signed their agreement. "
                    "Every enrolled member's agreement must be generated, printed and confirmed "
                    "before this chitti can start."
                ),
            })
        if not schedules:
            blockers.append({
                "code": "SCHEDULE_MISSING",
                "message": "This chitti has no period schedule, so no dues can be generated.",
            })

        return {
            "chitti_id": str(chitti.id),
            "status": chitti.status,
            "display_state": self._display_state(chitti.status, blockers),
            "can_activate": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "enrolled_members": enrolled,
            "active_members": active,
            "pending_agreements": pending_agreements,
            "member_capacity": chitti.member_count,
            "available_slots": max(chitti.member_count - enrolled, 0),
            "schedule_periods": len(schedules),
        }

    @staticmethod
    def _display_state(status: str, blockers: list[dict]) -> str:
        """Derived, display-only lifecycle label (no database state added)."""
        if status in ("DRAFT", "UPCOMING"):
            return "ACTIVATION_BLOCKED" if blockers else "READY_TO_START"
        if status == "RUNNING":
            return "ACTIVE"
        if status == "PAUSED":
            return "PAUSED"
        if status == "COMPLETED":
            return "COMPLETED"
        if status == "CANCELLED":
            return "CANCELLED"
        return status

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
        if existing and existing.status not in ("CANCELLED", "REJECTED"):
            raise ConflictException(
                "This member is already enrolled in this Chitti.",
                error_code="DUPLICATE_ENROLLMENT",
                details={
                    "customer_id": str(customer.id),
                    "chitti_id": str(chitti.id),
                    "existing_member_id": str(existing.id),
                    "existing_status": existing.status,
                },
            )

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

        # One query each for agreements and payouts, instead of per-member lookups,
        # so the Members tab can show agreement state and lifted amount in one call.
        from app.repositories.agreement_repo import ChittiAgreementRepository

        agreement_repo = ChittiAgreementRepository(self.session)
        agreements = {
            a.chitti_member_id: a
            for a in await agreement_repo.get_by_chitti_id(chitti.id)
        }
        lifted_by_member: dict = {}
        for payout in await self.payout_repo.get_by_chitti_id(chitti.id):
            lifted_by_member[payout.member_id] = (
                lifted_by_member.get(payout.member_id, Decimal("0"))
                + self._decimal(payout.net_payout)
            )

        result = []
        for m in members:
            customer = await self.customer_repo.get_by_id(m.customer_id)
            # Calculate totals from contributions
            contributions = await self.contribution_repo.get_by_member_id(m.id)
            total_expected = sum(c.expected_amount for c in contributions)
            total_paid = sum(c.paid_amount for c in contributions)
            agreement = agreements.get(m.id)
            agreement_summary = None
            if agreement:
                agreement_summary = {
                    "agreement_number": agreement.agreement_number,
                    "agreement_status": agreement.agreement_status,
                    "generated_at": str(agreement.generated_at) if agreement.generated_at else None,
                    "printed_at": str(agreement.printed_at) if agreement.printed_at else None,
                    "confirmed_at": str(agreement.confirmed_at) if agreement.confirmed_at else None,
                }
            result.append(self._member_to_dict(
                m, customer,
                total_expected=total_expected,
                total_paid=total_paid,
                agreement=agreement_summary,
                lifted_amount=lifted_by_member.get(m.id, Decimal("0")),
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

        # Due dates come from the period schedule and the actual receipts from the
        # transaction ledger — the same records the reports and detail view use.
        due_by_period = {}
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if chitti:
            for s in await self.schedule_repo.get_by_chitti_id(chitti.id):
                due_by_period[s.period_number] = str(s.due_date)

        payments_by_period: dict = {}
        for txn in await self.txn_repo.get_by_member_id(member_id):
            if txn.transaction_type != "CONTRIBUTION" or txn.member_id != member_id:
                continue
            payments_by_period.setdefault(txn.period_number, []).append({
                "id": str(txn.id),
                "amount": self._money(txn.amount),
                "payment_date": str(txn.payment_date) if txn.payment_date else None,
                "payment_method": txn.payment_method,
                "reference_number": txn.reference_number,
                "notes": txn.notes,
            })

        return [
            {
                "id": str(c.id),
                "member_id": str(c.member_id),
                "period_number": c.period_number,
                "due_date": due_by_period.get(c.period_number),
                "expected_amount": c.expected_amount,
                "paid_amount": c.paid_amount,
                "remaining_amount": c.remaining_amount,
                "status": c.status,
                "payments": payments_by_period.get(c.period_number, []),
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
            # A key belongs to exactly one contribution. Reusing it for a
            # different member/period/amount is a client bug, not a retry, and
            # must not silently return someone else's balance.
            if (
                str(existing_txn.member_id) != str(member.id)
                or existing_txn.period_number != period_number
                or existing_txn.amount != amount
            ):
                raise BadRequestException(
                    "This idempotency key was already used for a different contribution.",
                    error_code="IDEMPOTENCY_KEY_REUSED",
                )
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
        """Get summary for all active chittis (DRAFT, UPCOMING, RUNNING, PAUSED).

        member_count is the number of enrolled members (any agreement state
        except cancelled/rejected), which is the same number the Members tab
        lists. active_members and member_capacity are reported separately so
        callers never have to guess which meaning they hold.
        """
        result_chittis = []
        for status in ["RUNNING", "DRAFT", "UPCOMING", "PAUSED"]:
            chittis, _ = await self.chitti_repo.list_by_status(status, limit=100)
            result_chittis.extend(chittis)
        result = []
        for chitti in result_chittis:
            plan = await self.plan_repo.get_by_id(chitti.plan_id)
            enrolled_members = await self.member_repo.count_enrolled(chitti.id)
            active_members = await self.member_repo.count_active(chitti.id)
            pending_agreements = await self.member_repo.count_pending_agreements(
                chitti.id
            )
            schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)
            totals = await self._financial_totals(chitti, schedules=schedules)
            # Same rule as activation_status(): a DRAFT/UPCOMING chitti is only
            # ready once members exist, every agreement is signed, and periods exist.
            blocked = (
                chitti.status in ("DRAFT", "UPCOMING")
                and (
                    enrolled_members == 0
                    or active_members == 0
                    or pending_agreements > 0
                    or not schedules
                )
            )
            display_state = (
                "ACTIVATION_BLOCKED"
                if blocked
                else self._display_state(chitti.status, [])
            )

            next_period = next(
                (s for s in schedules if s.status in ("UPCOMING", "ACTIVE")), None
            )

            result.append({
                "id": str(chitti.id),
                "chitti_code": chitti.chitti_code,
                "name": chitti.name,
                "plan_name": plan.name if plan else None,
                "status": chitti.status,
                "display_state": display_state,
                "member_count": enrolled_members,
                "enrolled_members": enrolled_members,
                "active_members": active_members,
                "pending_agreements": pending_agreements,
                "member_capacity": chitti.member_count,
                "current_period": chitti.current_period,
                "total_periods": chitti.plan_snapshot.get("duration", 0),
                "total_value": self._money(chitti.total_value),
                "expected_collection": self._money(totals["expected"]),
                "actual_collection": self._money(totals["collected"]),
                "pending_collection": self._money(totals["pending"]),
                "financials_source": totals["source"],
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
        enrolled_members = await self.member_repo.count_enrolled(chitti.id)
        active_members = await self.member_repo.count_active(chitti.id)
        schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)
        payouts = await self.payout_repo.get_by_chitti_id(chitti.id)
        totals = await self._financial_totals(chitti, schedules=schedules)
        activation = await self.activation_status(chitti)

        total_payouts = sum(
            (self._decimal(p.net_payout) for p in payouts if p.status == "PAID"),
            Decimal("0"),
        )

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
            "display_state": activation["display_state"],
            # member_count stays the plan capacity for backwards compatibility;
            # enrolled_members is the number of members actually holding a place.
            "member_count": chitti.member_count,
            "member_capacity": chitti.member_count,
            "enrolled_members": enrolled_members,
            "active_members": active_members,
            "current_period": chitti.current_period,
            "total_periods": chitti.plan_snapshot.get("duration", 0),
            "total_value": self._money(chitti.total_value),
            "expected_collection": self._money(totals["expected"]),
            "actual_collection": self._money(totals["collected"]),
            "pending_collection": self._money(totals["pending"]),
            "financials_source": totals["source"],
            "total_payouts": self._money(total_payouts),
            "outstanding": self._money(totals["expected"] - totals["collected"]),
            "activation": activation,
            "next_due_date": str(next_period.due_date) if next_period else None,
            "next_payout_date": str(next_payout.paid_at) if next_payout else None,
        }

    # ===========================================================================
    # Helpers
    # ===========================================================================

    async def _financial_totals(self, chitti, schedules=None) -> dict:
        """Money totals for a chitti from one consistent source.

        Contribution rows are authoritative because record_contribution writes
        them and refreshes member aggregates from them. Period schedules are
        only a fallback for chittis created before any contribution row existed,
        and that fallback is logged rather than hidden.
        """
        contributions = await self.contribution_repo.get_by_chitti_id(chitti.id)
        if contributions:
            return {
                "expected": sum(
                    (self._decimal(c.expected_amount) for c in contributions), Decimal("0")
                ),
                "collected": sum(
                    (self._decimal(c.paid_amount) for c in contributions), Decimal("0")
                ),
                "pending": sum(
                    (self._decimal(c.remaining_amount) for c in contributions), Decimal("0")
                ),
                "source": "contributions",
            }

        # A started chitti must always have contribution rows; if it does not
        # (legacy data), fall back to the period schedule instead of showing 0.
        if chitti.status in ("RUNNING", "PAUSED", "COMPLETED"):
            if schedules is None:
                schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)
            logger.warning(
                "Chitti %s (%s) has no contribution rows; falling back to period schedule totals",
                chitti.chitti_code,
                chitti.status,
            )
            return {
                "expected": sum(
                    (self._decimal(s.expected_collection) for s in schedules), Decimal("0")
                ),
                "collected": sum(
                    (self._decimal(s.actual_collection) for s in schedules), Decimal("0")
                ),
                "pending": sum(
                    (self._decimal(s.pending_collection) for s in schedules), Decimal("0")
                ),
                "source": "schedule",
            }

        # Not started yet: no member dues have been generated, so reporting the
        # plan-wide schedule total here would overstate pending money.
        return {
            "expected": Decimal("0"),
            "collected": Decimal("0"),
            "pending": Decimal("0"),
            "source": "not_generated",
        }

    @staticmethod
    def _decimal(value) -> Decimal:
        """Coerce a stored money value to a finite Decimal, logging bad input.

        Returning 0 for genuinely invalid data would hide a financial bug, so
        every conversion failure and every non-finite value is logged loudly.
        """
        if value is None:
            logger.warning("Money value is NULL; treated as 0")
            return Decimal("0")
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, bool):
            logger.error("Boolean used as money value: %r", value)
            return Decimal("0")
        else:
            try:
                result = Decimal(str(value))
            except (InvalidOperation, ValueError):
                logger.error("Unparseable money value: %r", value)
                return Decimal("0")
        if not result.is_finite():
            logger.error("Non-finite money value %r coerced to 0", value)
            return Decimal("0")
        return result

    @classmethod
    def _money(cls, value) -> float:
        """Money as a JSON-safe float (never NaN/Infinity)."""
        return float(cls._decimal(value))

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

    async def _sync_period_schedules_from_contributions(self, chitti) -> None:
        """Rebuild period expected/paid/pending from member contributions.

        A chitti is created with a schedule projected from the plan capacity
        (e.g. 25 seats), but only enrolled members contribute. Leaving that
        projection in place inflated expected, pending and overdue on every
        schedule-based screen.
        """
        contributions = await self.contribution_repo.get_by_chitti_id(chitti.id)
        if not contributions:
            return

        aggregates: dict[int, dict] = {}
        for con in contributions:
            entry = aggregates.setdefault(
                con.period_number,
                {"expected": Decimal("0"), "paid": Decimal("0")},
            )
            entry["expected"] += con.expected_amount
            entry["paid"] += con.paid_amount

        for schedule in await self.schedule_repo.get_by_chitti_id(chitti.id):
            entry = aggregates.get(schedule.period_number)
            if entry is None:
                continue
            expected = entry["expected"]
            paid = entry["paid"]
            await self.schedule_repo.update(
                schedule,
                expected_collection=expected,
                actual_collection=paid,
                pending_collection=max(expected - paid, Decimal("0")),
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

    def _chitti_to_dict(
        self,
        chitti,
        plan_name: Optional[str] = None,
        enrolled_members: Optional[int] = None,
    ) -> dict:
        return {
            "id": str(chitti.id),
            "chitti_code": chitti.chitti_code,
            "plan_id": str(chitti.plan_id),
            "plan_name": plan_name,
            "name": chitti.name,
            "branch": chitti.branch,
            "start_date": str(chitti.start_date),
            "end_date": str(chitti.end_date),
            # member_count is the plan capacity (backwards compatible).
            "member_count": chitti.member_count,
            "member_capacity": chitti.member_count,
            "enrolled_members": enrolled_members,
            "total_value": self._money(chitti.total_value),
            "current_period": chitti.current_period,
            "status": chitti.status,
            "notes": chitti.notes,
            "plan_snapshot": chitti.plan_snapshot,
            "created_by": str(chitti.created_by) if chitti.created_by else None,
            "created_at": str(chitti.created_at),
            "updated_at": str(chitti.updated_at),
        }

    def _member_to_dict(
        self,
        member,
        customer=None,
        total_expected=Decimal("0"),
        total_paid=Decimal("0"),
        agreement=None,
        lifted_amount=Decimal("0"),
    ) -> dict:
        return {
            "lifted": bool(member.lifted),
            "lifted_at": str(member.lifted_at) if member.lifted_at else None,
            "lift_period": member.lift_period,
            "lifted_amount": self._money(lifted_amount),
            "agreement": agreement,
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
            "total_expected": self._money(total_expected),
            "total_paid": self._money(total_paid),
            "outstanding": self._money(self._decimal(total_expected) - self._decimal(total_paid)),
        }
