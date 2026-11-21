"""
Chitti service — orchestrates plans, instances, members, schedules, contributions, payouts.

All business logic lives here. API handlers should only call service methods.
"""

import logging
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
    ENROLLED_EXCLUDED_STATUSES,
    ChittiContributionRepository,
    ChittiLiftEventRepository,
    ChittiMemberRepository,
    ChittiPayoutRepository,
    ChittiPeriodScheduleRepository,
    ChittiPlanRepository,
    ChittiPaymentAllocationRepository,
    ChittiRepository,
    ChittiTransactionRepository,
)
from app.repositories.customer_repo import CustomerRepository
from app.models.chitti import ChittiLiftEvent, ChittiPlan
from app.services.chitti_calculation import ChittiCalculationEngine
from app.services.audit_service import AuditService
from app.utils.codes import generate_chitti_code, generate_plan_code
from app.utils.timezone import make_aware, today_ist

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
        self.allocation_repo = ChittiPaymentAllocationRepository(session)
        self.lift_repo = ChittiLiftEventRepository(session)
        self.customer_repo = CustomerRepository(session)

    # ===========================================================================
    # Plan CRUD
    # ===========================================================================

    async def create_plan(self, *, data: dict, created_by: Optional[UUID] = None) -> dict:
        """Create a new Chitti plan with validated rules."""
        # Validate rules
        try:
            validate_contribution_rules(data["contribution_rules"])
            validate_payout_rules(data["payout_rules"])
        except (ValueError, TypeError) as exc:
            raise BadRequestException(f"Invalid Chitti rule configuration: {exc}", error_code="INVALID_CHITTI_RULES") from exc

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

    async def preview_direct_chitti(self, data: dict) -> dict:
        try:
            validate_contribution_rules(data["contribution_rules"])
            validate_payout_rules(data["payout_rules"])
        except (ValueError, TypeError) as exc:
            raise BadRequestException(f"Invalid Chitti rule configuration: {exc}", error_code="INVALID_CHITTI_RULES") from exc
        self._validate_direct_configuration(data)
        snapshot = {
            "chitti_type": data["chitti_type"], "total_value": data["total_value"],
            "member_count": data["member_count"], "frequency": data["frequency"],
            "duration": data["duration"], "contribution_rules": data["contribution_rules"],
            "payout_rules": data["payout_rules"], "fee_rules": data.get("fee_rules") or {},
            "penalty_rules": data.get("penalty_rules") or {},
        }
        engine = ChittiCalculationEngine(snapshot)
        if snapshot["contribution_rules"].get("type") == "FIXED":
            snapshot["total_value"] = engine.calculate_fixed_total_value(data["member_count"])
            engine = ChittiCalculationEngine(snapshot)
        preview = engine.preview_full_schedule(data["start_date"], data["member_count"])
        return {**preview, "plan_name": data["name"], "chitti_type": data["chitti_type"],
            "frequency": data["frequency"], "duration": data["duration"],
            "member_count": data["member_count"], "total_value": snapshot["total_value"]}

    async def preview_chitti(
        self,
        plan_id: UUID,
        start_date,
        member_count: Optional[int] = None,
        frequency: Optional[str] = None,
        duration: Optional[int] = None,
        total_value: Optional[Decimal] = None,
        contribution_rules: Optional[dict] = None,
    ) -> dict:
        """Generate a full preview of a chitti before creation."""
        plan = await self.plan_repo.get_by_id(plan_id)
        if not plan:
            raise NotFoundException("Chitti plan", plan_id)

        mc = member_count or plan.member_count
        snapshot = self._build_plan_snapshot(plan)
        snapshot["member_count"] = mc
        if frequency:
            snapshot["frequency"] = frequency
        if duration:
            snapshot["duration"] = duration
        if contribution_rules:
            validate_contribution_rules(contribution_rules)
            snapshot["contribution_rules"] = contribution_rules
        if total_value is not None:
            snapshot["total_value"] = total_value
        engine = ChittiCalculationEngine(snapshot)
        if snapshot["contribution_rules"].get("type") == "FIXED":
            snapshot["total_value"] = engine.calculate_fixed_total_value(mc)
            engine = ChittiCalculationEngine(snapshot)
        preview = engine.preview_full_schedule(start_date, mc)

        return {
            **preview,
            "plan_name": plan.name,
            "chitti_type": plan.chitti_type,
            "frequency": snapshot["frequency"],
            "duration": snapshot["duration"],
            "member_count": mc,
            "total_value": snapshot["total_value"],
        }

    # ===========================================================================
    # Chitti Instance CRUD
    # ===========================================================================

    async def create_chitti(self, *, data: dict, created_by: Optional[UUID] = None) -> dict:
        """Create a chitti instance from a plan. Creates plan snapshot + schedule + member slots."""
        plan_id = data.get("plan_id")
        if not plan_id:
            required = ("chitti_type", "total_value", "member_count", "frequency", "duration", "start_date", "contribution_rules", "payout_rules")
            missing = [field for field in required if data.get(field) is None]
            if missing:
                raise BadRequestException(
                    "Direct Chitti creation requires: " + ", ".join(missing),
                    error_code="DIRECT_CHITTI_CONFIGURATION_INCOMPLETE",
                )
            try:
                validate_contribution_rules(data["contribution_rules"])
                validate_payout_rules(data["payout_rules"])
            except (ValueError, TypeError) as exc:
                raise BadRequestException(f"Invalid Chitti rule configuration: {exc}", error_code="INVALID_CHITTI_RULES") from exc
            self._validate_direct_configuration(data)
            if data["contribution_rules"].get("type") == "FIXED":
                fixed_engine = ChittiCalculationEngine({
                    "total_value": data["total_value"], "member_count": data["member_count"],
                    "duration": data["duration"], "frequency": data["frequency"],
                    "contribution_rules": data["contribution_rules"],
                    "payout_rules": data["payout_rules"],
                })
                data["total_value"] = fixed_engine.calculate_fixed_total_value(data["member_count"])
            # Preserve the existing immutable plan snapshot and calculation engine.
            # The UI can create directly; an internal plan record remains the
            # authoritative reusable rule snapshot linked to the Chitti.
            direct_plan = await self.create_plan(data={
                "name": data["name"],
                "description": "Configuration captured when Chitti was created.",
                "chitti_type": data["chitti_type"],
                "total_value": data["total_value"],
                "currency": "INR",
                "member_count": data["member_count"],
                "frequency": data["frequency"],
                "duration": data["duration"],
                "contribution_rules": data["contribution_rules"],
                "payout_rules": data["payout_rules"],
                "fee_rules": data.get("fee_rules") or {},
                "penalty_rules": data.get("penalty_rules") or {},
            }, created_by=created_by)
            plan_id = direct_plan["id"]
        plan = await self.plan_repo.get_by_id(UUID(plan_id))
        if not plan:
            raise NotFoundException("Chitti plan", plan_id)
        if not plan.is_active:
            raise BadRequestException("Cannot create chitti from an inactive plan.")

        member_count = data.get("member_count") or plan.member_count
        if member_count < 1:
            raise BadRequestException("Member count must be at least 1.")

        # A saved plan is a reusable rule template. The new instance snapshots
        # its selected overrides instead of blindly copying its old total.
        snapshot = self._build_plan_snapshot(plan)
        member_count = int(data.get("member_count") or plan.member_count)
        snapshot["member_count"] = member_count
        for key in ("chitti_type", "total_value", "frequency", "duration", "contribution_rules",
                    "payout_rules", "fee_rules", "penalty_rules"):
            if data.get(key) is not None:
                snapshot[key] = data[key]
        if snapshot["contribution_rules"].get("type") not in ("FIXED", "LIFT_BASED"):
            raise BadRequestException("New Chittis must use Fixed or Lift-based contribution rules.")
        try:
            validate_contribution_rules(snapshot["contribution_rules"])
            validate_payout_rules(snapshot["payout_rules"])
        except (ValueError, TypeError) as exc:
            raise BadRequestException(f"Invalid Chitti rule configuration: {exc}", error_code="INVALID_CHITTI_RULES") from exc
        if snapshot["contribution_rules"].get("type") == "FIXED":
            snapshot["total_value"] = str(ChittiCalculationEngine(snapshot).calculate_fixed_total_value(member_count))
        elif data.get("total_value") is not None:
            snapshot["total_value"] = str(data["total_value"])
        engine = ChittiCalculationEngine(snapshot)

        # Calculate end date
        from app.services.chitti_calculation import FREQUENCY_DAYS
        from datetime import timedelta
        frequency = snapshot["frequency"]
        duration = int(snapshot["duration"])
        days_per_period = FREQUENCY_DAYS.get(frequency, 30)
        total_days = days_per_period * duration
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
            total_value=snapshot["total_value"],
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

    @staticmethod
    def _validate_direct_configuration(data: dict) -> None:
        duration = int(data["duration"])
        members = int(data["member_count"])
        contribution = data["contribution_rules"]
        if contribution.get("type") in ("CUSTOM", "SCHEDULE"):
            entries = contribution.get("schedule", [])
            periods = [int(entry.get("period", 0)) for entry in entries]
            if sorted(periods) != list(range(1, duration + 1)):
                raise BadRequestException(
                    "Contribution schedule must define exactly one amount for every period.",
                    error_code="INCOMPLETE_CONTRIBUTION_SCHEDULE",
                )
        payout = data["payout_rules"]
        if payout.get("type") == "CUSTOM":
            entries = payout.get("payout_schedule", [])
            periods = [int(entry.get("period", 0)) for entry in entries]
            winners = [int(entry.get("member_number", 0)) for entry in entries]
            if sorted(periods) != list(range(1, duration + 1)):
                raise BadRequestException(
                    "Custom winner rules must define exactly one winner for every period.",
                    error_code="INCOMPLETE_WINNER_SCHEDULE",
                )
            if any(number < 1 or number > members for number in winners):
                raise BadRequestException(
                    "Every custom winner must reference a member number within the configured capacity.",
                    error_code="INVALID_WINNER_MEMBER_NUMBER",
                )

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
        if enrolled != chitti.member_count:
            blockers.append({
                "code": "MEMBER_COUNT_MISMATCH",
                "message": (
                    f"Chitti requires exactly {chitti.member_count} member(s), "
                    f"but {enrolled} are currently enrolled. Add or remove members "
                    "until the counts match before starting."
                ),
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
        self, chitti_id: UUID, *, customer_id: str, member_number: Optional[int] = None,
        payout_order: Optional[int] = None, alias: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> dict:
        """Enroll a member through the same path the API uses.

        ``member_number`` is accepted for source compatibility with older
        callers but is no longer trusted: both paths now assign max + 1 while
        holding the Chitti row lock. The agreement workflow owns status,
        contribution generation and audit logging for every enrollment.
        """
        from app.services.agreement_service import AgreementService

        return await AgreementService(self.session).add_member(
            chitti_id,
            customer_id=customer_id,
            payout_order=payout_order,
            alias=alias,
            created_by=created_by,
        )

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
        all_contributions = await self.contribution_repo.get_by_chitti_id(chitti.id)
        effective_values = await self._effective_contribution_values(chitti, all_contributions)
        allocation_rows = await self.allocation_repo.get_by_chitti_id(chitti.id)
        credits_by_member = self._unallocated_credit_by_member(allocation_rows)
        unresolved_by_member: dict[UUID, Decimal] = {}
        for row in allocation_rows:
            if row.allocation_type == "UNRESOLVED":
                unresolved_by_member[row.member_id] = (
                    unresolved_by_member.get(row.member_id, Decimal("0"))
                    + self._decimal(row.amount)
                )
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
            total_expected = sum((effective_values[c.id]["expected"] for c in contributions), Decimal("0"))
            allocated_paid = sum((c.paid_amount for c in contributions), Decimal("0"))
            credit = credits_by_member.get(m.id, Decimal("0"))
            unresolved = unresolved_by_member.get(m.id, Decimal("0"))
            total_paid = allocated_paid
            outstanding = sum(
                (effective_values[c.id]["remaining"] for c in contributions),
                Decimal("0"),
            )
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
                unallocated_credit=credit,
                unresolved_excess=unresolved,
                outstanding=outstanding,
            ))
        return result

    async def get_member_for_chitti(self, chitti_id: UUID, member_id: UUID):
        """Return a member only when it belongs to the Chitti in the URL.

        Agreement/cancellation routes carry both identifiers. Without this check
        a member of another Chitti could be modified through a mismatched URL.
        """
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        member = await self.member_repo.get_by_id(member_id)
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)
        return member

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
        effective_values = await self._effective_contribution_values(chitti)
        total_expected = sum((effective_values[c.id]["expected"] for c in contributions), Decimal("0"))
        allocated_paid = sum((c.paid_amount for c in contributions), Decimal("0"))
        member_allocations = await self.allocation_repo.get_by_member_id(
            chitti.id, member.id
        )
        credit = self._unallocated_credit(member_allocations)
        unresolved = sum(
            (
                self._decimal(row.amount)
                for row in member_allocations
                if row.allocation_type == "UNRESOLVED"
            ),
            Decimal("0"),
        )
        total_paid = allocated_paid
        outstanding = sum(
            (effective_values[c.id]["remaining"] for c in contributions),
            Decimal("0"),
        )

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
            "alias": getattr(member, "alias", None),
            "customer_code": customer.customer_code if customer else None,
            "mobile_number": customer.mobile_number if customer else None,
            "member_number": member.member_number,
            "payout_order": member.payout_order,
            "status": member.status,
            "joined_at": str(member.joined_at),
            "total_expected_amount": float(total_expected),
            "total_paid_amount": float(total_paid),
            "outstanding_amount": float(outstanding),
            "unallocated_credit": float(credit),
            "unresolved_excess": float(unresolved),
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
        return await self._effective_schedule_rows(chitti, schedules)

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
        effective_values = await self._effective_contribution_values(chitti, contributions) if chitti else {}

        transactions = await self.txn_repo.get_by_member_id(member_id)
        transaction_by_id = {txn.id: txn for txn in transactions}
        allocation_rows = await self.allocation_repo.get_by_member_id(
            UUID(str(chitti_id)), UUID(str(member_id))
        )
        payments_by_contribution: dict = {}
        allocated_sources = set()
        for allocation in allocation_rows:
            allocated_sources.add(allocation.source_transaction_id)
            if allocation.event_transaction_id:
                allocated_sources.add(allocation.event_transaction_id)
            if allocation.allocation_type != "CONTRIBUTION" or not allocation.contribution_id:
                continue
            source = transaction_by_id.get(allocation.source_transaction_id)
            event = transaction_by_id.get(allocation.event_transaction_id)
            if allocation.event_type == "PAYMENT":
                transaction_type = "CONTRIBUTION"
            elif allocation.event_type == "REVERSAL":
                transaction_type = "REVERSAL"
            else:
                transaction_type = allocation.event_type
            display_transaction = event or source
            payments_by_contribution.setdefault(allocation.contribution_id, []).append({
                "id": str(allocation.id),
                "transaction_id": str(display_transaction.id) if display_transaction else None,
                "amount": self._money(allocation.amount),
                "transaction_type": transaction_type,
                "payment_date": (
                    str(display_transaction.payment_date)
                    if display_transaction and display_transaction.payment_date else None
                ),
                "payment_method": display_transaction.payment_method if display_transaction else None,
                "reference_number": display_transaction.reference_number if display_transaction else None,
                "notes": display_transaction.notes if display_transaction else None,
            })

        # Historical transactions predate allocation rows. Keep their original
        # period association; do not synthesize links across other periods.
        for txn in transactions:
            if (
                txn.transaction_type not in ("CONTRIBUTION", "REVERSAL")
                or txn.id in allocated_sources
                or not txn.period_number
            ):
                continue
            contribution = next(
                (row for row in contributions if row.period_number == txn.period_number),
                None,
            )
            if contribution:
                payments_by_contribution.setdefault(contribution.id, []).append({
                    "id": str(txn.id),
                    "transaction_id": str(txn.id),
                    "amount": self._money(
                        -txn.amount if txn.transaction_type == "REVERSAL" else txn.amount
                    ),
                    "transaction_type": txn.transaction_type,
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
                "expected_amount": effective_values.get(c.id, {}).get("expected", c.expected_amount),
                "paid_amount": effective_values.get(c.id, {}).get("paid", c.paid_amount),
                "remaining_amount": effective_values.get(c.id, {}).get("remaining", c.remaining_amount),
                "status": "PAID" if effective_values.get(c.id, {}).get("remaining", c.remaining_amount) == 0 else c.status,
                "payments": payments_by_contribution.get(c.id, []),
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
        chitti = await self.chitti_repo.get_by_id_for_update(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        if chitti.status != "RUNNING":
            raise BadRequestException("Chitti is not in RUNNING status.")

        member = await self.member_repo.get_by_id_for_update(UUID(member_id))
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)

        # Lock the member-period balance before rechecking idempotency or
        # eligibility. Concurrent clicks with distinct keys serialize here.
        selected_contribution = await self.contribution_repo.get_by_chitti_member_period_for_update(
            chitti.id, member.id, period_number
        )
        if not selected_contribution:
            raise NotFoundException("Contribution entry for this period")

        # Idempotency — recheck after acquiring the balance lock so a request
        # waiting behind its identical in-flight retry returns that receipt.
        existing_txn = await self.txn_repo.get_by_idempotency_key(idempotency_key)
        if existing_txn:
            # A key belongs to exactly one contribution. Reusing it for a
            # different member/period/amount is a client bug, not a retry, and
            # must not silently return someone else's balance.
            if (
                existing_txn.chitti_id != chitti.id
                or existing_txn.transaction_type != "CONTRIBUTION"
                or str(existing_txn.member_id) != str(member.id)
                or existing_txn.period_number != period_number
                or existing_txn.amount != amount
            ):
                raise BadRequestException(
                    "This idempotency key was already used for a different contribution.",
                    error_code="IDEMPOTENCY_KEY_REUSED",
                )
            prior = selected_contribution
            prior_allocations = await self.allocation_repo.get_by_source_transaction_id(
                existing_txn.id
            )
            prior_member_contributions = await self.contribution_repo.get_by_member_id(
                member.id
            )
            returned_allocations = [
                {
                    "period_number": next(
                        (
                            row.period_number
                            for row in prior_member_contributions
                            if row.id == allocation.contribution_id
                        ),
                        None,
                    ),
                    "contribution_id": str(allocation.contribution_id),
                    "amount": self._money(allocation.amount),
                }
                for allocation in prior_allocations
                if allocation.event_type == "PAYMENT"
                and allocation.allocation_type == "CONTRIBUTION"
                and allocation.contribution_id
            ]
            original_credit = sum(
                (
                    allocation.amount
                    for allocation in prior_allocations
                    if allocation.event_type == "PAYMENT"
                    and allocation.allocation_type == "CREDIT"
                ),
                Decimal("0"),
            )
            original_unresolved = sum(
                (
                    allocation.amount
                    for allocation in prior_allocations
                    if allocation.event_type == "PAYMENT"
                    and allocation.allocation_type == "UNRESOLVED"
                ),
                Decimal("0"),
            )
            return {
                "transaction_id": str(existing_txn.id),
                "contribution_id": str(prior.id) if prior else None,
                "paid_amount": self._money(prior.paid_amount) if prior else 0.0,
                "remaining_amount": self._money(prior.remaining_amount) if prior else 0.0,
                "status": prior.status if prior else "UNKNOWN",
                "allocated_amount": sum(
                    (row["amount"] for row in returned_allocations), 0.0
                ),
                "unallocated_credit": self._money(original_credit),
                "unresolved_excess": self._money(original_unresolved),
                "allocations": returned_allocations,
                "duplicate": True,
            }

        member_contributions = await self.contribution_repo.get_by_member_id(member.id)
        effective_values = await self._effective_contribution_values(chitti, member_contributions)
        ordered_contributions = sorted(member_contributions, key=lambda row: row.period_number)
        earliest_outstanding = next(
            (
                row for row in ordered_contributions
                if effective_values[row.id]["remaining"] > 0
            ),
            None,
        )
        if (
            earliest_outstanding
            and effective_values[selected_contribution.id]["remaining"] <= 0
            and period_number < earliest_outstanding.period_number
        ):
            raise BadRequestException(
                "This contribution period is already fully paid.",
                error_code="CONTRIBUTION_PERIOD_ALREADY_PAID",
            )
        if earliest_outstanding and earliest_outstanding.period_number != period_number:
            raise BadRequestException(
                f"Collect the earliest outstanding period first (period {earliest_outstanding.period_number}).",
                error_code="EARLIEST_DUE_PERIOD_REQUIRED",
            )
        contribution = selected_contribution
        effective = effective_values[contribution.id]
        if not amount.is_finite() or amount <= 0:
            raise BadRequestException("Payment amount must be greater than zero.")
        rules = (chitti.plan_snapshot or {}).get("contribution_rules", {})
        partial_allowed = rules.get("partial_payments_allowed") is True
        if (
            effective["remaining"] > 0
            and amount < effective["remaining"]
            and not partial_allowed
        ):
            raise BadRequestException(
                "Partial payments are not enabled for this Chitti contribution.",
                error_code="PARTIAL_PAYMENT_NOT_ALLOWED",
            )
        if not earliest_outstanding:
            schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)
            if period_number < 1 or period_number > len(schedules):
                raise BadRequestException("Contribution period is outside the Chitti schedule.")

        # Record transaction with the business date and idempotency key.
        transaction = await self.txn_repo.create(
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

        amount_left = amount
        allocation_details = []
        contribution_updates = ordered_contributions[
            next(
                (
                    index for index, row in enumerate(ordered_contributions)
                    if row.period_number == period_number
                ),
                len(ordered_contributions),
            ):
        ]
        for row in contribution_updates:
            remaining = effective_values[row.id]["remaining"]
            if remaining <= 0 or amount_left <= 0:
                continue
            if not partial_allowed and amount_left < remaining:
                break
            applied = min(amount_left, remaining)
            new_paid = self._decimal(row.paid_amount) + applied
            new_remaining = max(
                effective_values[row.id]["expected"] - new_paid,
                Decimal("0"),
            )
            new_status = (
                "PAID" if new_remaining == 0
                else "PARTIALLY_PAID" if new_paid > 0
                else row.status
            )
            await self.contribution_repo.update(
                row,
                expected_amount=effective_values[row.id]["expected"],
                paid_amount=new_paid,
                remaining_amount=new_remaining,
                status=new_status,
            )
            await self.allocation_repo.create(
                chitti_id=chitti.id,
                member_id=member.id,
                source_transaction_id=transaction.id,
                event_transaction_id=transaction.id,
                contribution_id=row.id,
                allocation_type="CONTRIBUTION",
                event_type="PAYMENT",
                amount=applied,
            )
            allocation_details.append({
                "period_number": row.period_number,
                "contribution_id": str(row.id),
                "amount": applied,
            })
            amount_left -= applied

        if amount_left > 0:
            # Cash received beyond the payable instalments is not credit yet: the
            # operator must decide what it pays for. Keep it visible as unresolved
            # excess until an explicit excess resolution converts it.
            await self.allocation_repo.create(
                chitti_id=chitti.id,
                member_id=member.id,
                source_transaction_id=transaction.id,
                event_transaction_id=transaction.id,
                contribution_id=None,
                allocation_type="UNRESOLVED",
                event_type="PAYMENT",
                amount=amount_left,
            )
        await self._sync_period_schedules_from_contributions(chitti)
        await self._refresh_member_financials(chitti, member)
        await AuditService(self.session).log(
            user_id=created_by,
            action="CHITTI_CONTRIBUTION_RECORDED",
            entity_type="chitti_transaction",
            entity_id=transaction.id,
            new_value={
                "chitti_id": str(chitti.id),
                "member_id": str(member.id),
                "transaction_id": str(transaction.id),
                "contribution_id": str(contribution.id),
                "period_number": period_number,
                "amount": str(amount),
                "allocations": [
                    {
                        "period_number": item["period_number"],
                        "contribution_id": item["contribution_id"],
                        "amount": str(item["amount"]),
                    }
                    for item in allocation_details
                ],
                "unallocated_credit": str(amount_left),
                "payment_method": payment_method,
                "payment_date": str(transaction.payment_date),
            },
        )

        return {
            "transaction_id": str(transaction.id),
            "contribution_id": str(contribution.id),
            "paid_amount": self._money(contribution.paid_amount),
            "remaining_amount": self._money(contribution.remaining_amount),
            "status": contribution.status,
            "allocated_amount": self._money(amount - amount_left),
            "unallocated_credit": 0.0,
            "unresolved_excess": self._money(amount_left),
            "allocations": [
                {**item, "amount": self._money(item["amount"])}
                for item in allocation_details
            ],
            "duplicate": False,
        }

    async def reverse_contribution(
        self, chitti_id: UUID, transaction_id: UUID, *, reason: str,
        reversed_by: Optional[UUID] = None,
    ) -> dict:
        """Reverse a Chitti contribution by adding a ledger row and restoring dues."""
        chitti = await self.chitti_repo.get_by_id_for_update(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        original = await self.txn_repo.get_by_id_for_update(transaction_id)
        if not original or original.chitti_id != chitti.id:
            raise NotFoundException("Chitti transaction", transaction_id)
        if original.transaction_type != "CONTRIBUTION" or not original.member_id or not original.period_number:
            raise BadRequestException("Only contribution transactions can be reversed.")
        key = f"reversal-{original.id}"
        existing = await self.txn_repo.get_by_idempotency_key(key)
        if existing:
            return {"transaction_id": str(existing.id), "original_transaction_id": str(original.id), "amount": float(existing.amount), "duplicate": True}
        member = await self.member_repo.get_by_id_for_update(original.member_id)
        if not member:
            raise BadRequestException("The contribution member no longer exists.")
        allocations = await self.allocation_repo.get_by_source_transaction_id(original.id)
        allocated_by_contribution: dict[UUID, Decimal] = {}
        allocated_credit = Decimal("0")
        for allocation in allocations:
            if allocation.allocation_type == "CREDIT":
                allocated_credit += allocation.amount
            elif allocation.contribution_id:
                allocated_by_contribution[allocation.contribution_id] = (
                    allocated_by_contribution.get(allocation.contribution_id, Decimal("0"))
                    + allocation.amount
                )

        # Money already handed back to the customer must not be reversed twice.
        refunded = await self._refunded_amount(original.id)
        net_amount = self._decimal(original.amount) - refunded
        if net_amount <= 0:
            raise BadRequestException(
                "This receipt has been fully refunded and cannot be reversed.",
                error_code="RECEIPT_FULLY_REFUNDED",
            )
        if allocations and sum(
            (row.amount for row in allocations), Decimal("0")
        ) != net_amount:
            raise BadRequestException(
                "Payment allocation history does not reconcile to the original receipt.",
                error_code="PAYMENT_ALLOCATION_MISMATCH",
            )

        reversal = await self.txn_repo.create(
            chitti_id=chitti.id, transaction_type="REVERSAL", member_id=original.member_id,
            amount=net_amount, payment_method=original.payment_method,
            reference_number=original.reference_number, period_number=original.period_number,
            notes=f"Reversal of {original.id}: {reason}", payment_date=today_ist(),
            idempotency_key=key, created_by=reversed_by,
            original_transaction_id=original.id,
        )

        if allocations:
            contributions = await self.contribution_repo.get_by_member_id(member.id)
            contribution_by_id = {row.id: row for row in contributions}
            ordered_ids = sorted(
                allocated_by_contribution,
                key=lambda contribution_id: (
                    contribution_by_id[contribution_id].period_number
                    if contribution_id in contribution_by_id else 0
                ),
            )
            for contribution_id in ordered_ids:
                amount_to_reverse = allocated_by_contribution[contribution_id]
                if contribution_id not in contribution_by_id:
                    raise BadRequestException(
                        "Payment allocation references a missing contribution.",
                        error_code="PAYMENT_ALLOCATION_MISMATCH",
                    )
                if amount_to_reverse < 0:
                    raise BadRequestException(
                        "Payment allocation history has a negative installment balance.",
                        error_code="PAYMENT_ALLOCATION_MISMATCH",
                    )
                if amount_to_reverse == 0:
                    continue
                contribution = contribution_by_id[contribution_id]
                if contribution.paid_amount < amount_to_reverse:
                    raise BadRequestException(
                        "Contribution balances do not support this reversal."
                    )
                effective = await self._effective_contribution_values(
                    chitti, [contribution]
                )
                new_paid = contribution.paid_amount - amount_to_reverse
                expected = effective[contribution.id]["expected"]
                new_remaining = max(expected - new_paid, Decimal("0"))
                schedule = await self.schedule_repo.get_by_period_for_update(
                    chitti.id, contribution.period_number
                )
                new_status = (
                    "PAID" if new_remaining == 0 and expected > 0
                    else "PARTIALLY_PAID" if new_paid > 0
                    else "OVERDUE" if schedule and schedule.due_date < today_ist()
                    else "UPCOMING"
                )
                await self.contribution_repo.update(
                    contribution,
                    expected_amount=expected,
                    paid_amount=new_paid,
                    remaining_amount=new_remaining,
                    status=new_status,
                )
                await self.allocation_repo.create(
                    chitti_id=chitti.id,
                    member_id=member.id,
                    source_transaction_id=original.id,
                    event_transaction_id=reversal.id,
                    contribution_id=contribution.id,
                    allocation_type="CONTRIBUTION",
                    event_type="REVERSAL",
                    amount=-amount_to_reverse,
                )
            if allocated_credit:
                await self.allocation_repo.create(
                    chitti_id=chitti.id,
                    member_id=member.id,
                    source_transaction_id=original.id,
                    event_transaction_id=reversal.id,
                    contribution_id=None,
                    allocation_type="CREDIT",
                    event_type="REVERSAL",
                    amount=-allocated_credit,
                )
        else:
            # Legacy receipts have only their original scalar period association.
            # Preserve that relationship; never fabricate cross-period allocations.
            contribution = await self.contribution_repo.get_by_chitti_member_period_for_update(
                chitti.id, original.member_id, original.period_number
            )
            if not contribution or contribution.paid_amount < net_amount:
                raise BadRequestException("Contribution balances do not support this reversal.")
            effective = await self._effective_contribution_values(chitti, [contribution])
            new_paid = contribution.paid_amount - net_amount
            expected = effective[contribution.id]["expected"]
            new_remaining = max(expected - new_paid, Decimal("0"))
            schedule = await self.schedule_repo.get_by_period_for_update(
                chitti.id, original.period_number
            )
            new_status = (
                "PAID" if new_remaining == 0 and expected > 0
                else "PARTIALLY_PAID" if new_paid > 0
                else "OVERDUE" if schedule and schedule.due_date < today_ist()
                else "UPCOMING"
            )
            await self.contribution_repo.update(
                contribution,
                expected_amount=expected,
                paid_amount=new_paid,
                remaining_amount=new_remaining,
                status=new_status,
            )

        await self._sync_period_schedules_from_contributions(chitti)
        await self._refresh_member_financials(chitti, member)
        from app.services.audit_service import AuditService
        await AuditService(self.session).log(
            user_id=reversed_by, action="CHITTI_CONTRIBUTION_REVERSED",
            entity_type="chitti_transaction", entity_id=reversal.id,
            previous_value={"transaction_id": str(original.id), "amount": str(original.amount)},
            new_value={"reason": reason, "reversal_id": str(reversal.id)},
        )
        return {
            "transaction_id": str(reversal.id),
            "original_transaction_id": str(original.id),
            "amount": float(reversal.amount),
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
        members = {
            member.id: member
            for member in await self.member_repo.get_by_chitti_id(chitti.id)
        }
        customer_names: dict[UUID, str | None] = {}
        for member in members.values():
            if member.customer_id not in customer_names:
                customer = await self.customer_repo.get_by_id(member.customer_id)
                customer_names[member.customer_id] = (
                    customer.full_name if customer else None
                )
        return [
            {
                "id": str(p.id),
                "chitti_id": str(p.chitti_id),
                "member_id": str(p.member_id),
                "customer_name": customer_names.get(
                    members[p.member_id].customer_id
                ) if p.member_id in members else None,
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

    async def list_lift_events(self, chitti_id: UUID) -> list[dict]:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        members = {member.id: member for member in await self.member_repo.get_by_chitti_id(chitti.id)}
        events = await self.lift_repo.get_by_chitti_id(chitti.id)
        result = []
        for event in events:
            member = members.get(event.member_id)
            customer = await self.customer_repo.get_by_id(member.customer_id) if member else None
            result.append({
                "id": str(event.id), "chitti_id": str(event.chitti_id),
                "member_id": str(event.member_id),
                "member_number": member.member_number if member else None,
                "member_name": customer.full_name if customer else None,
                "period_number": event.period_number, "lift_date": str(event.lift_date),
                "recorded_by": str(event.recorded_by) if event.recorded_by else None,
                "reversed_at": str(event.reversed_at) if event.reversed_at else None,
                "reversal_reason": event.reversal_reason,
            })
        return result

    async def record_lift(
        self, chitti_id: UUID, *, member_id: str, period_number: int,
        lift_date: date, recorded_by: Optional[UUID],
    ) -> dict:
        """Record the lift event and recalculate only that member's lift period onward."""
        chitti = await self.chitti_repo.get_by_id_for_update(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        snapshot = chitti.plan_snapshot or {}
        rules = snapshot.get("contribution_rules", {}) or {}
        if rules.get("type") != "LIFT_BASED":
            raise BadRequestException("Lift events are available only for Lift-based Chittis.")
        if chitti.status != "RUNNING":
            raise BadRequestException("A lift can be recorded only for a running Chitti.")
        if lift_date > today_ist():
            raise BadRequestException("Lift date cannot be in the future.")
        member = await self.member_repo.get_by_id_for_update(UUID(member_id))
        if not member or member.chitti_id != chitti.id or member.status != "ACTIVE":
            raise BadRequestException("Select an active member enrolled in this Chitti.")
        duration = int(snapshot.get("duration", 0))
        if period_number < 1 or period_number > duration:
            raise BadRequestException("Lift period is outside the Chitti schedule.")
        schedule = await self.schedule_repo.get_by_period_for_update(chitti.id, period_number)
        if not schedule or schedule.due_date > lift_date:
            raise BadRequestException("The selected lift period is not eligible on this lift date.")
        # Lift history is per membership slot. Another slot in this Chitti may
        # lift in the same period, but this slot must not lift twice.
        existing = await self.lift_repo.get_active_by_member_and_period(
            chitti.id, member.id, period_number
        )
        if existing and existing.reversed_at is None:
            raise ConflictException(
                "A lift is already recorded for this period.",
                error_code="DUPLICATE_LIFT_PERIOD",
            )
        event = await self.lift_repo.create(
            chitti_id=chitti.id, member_id=member.id, period_number=period_number,
            lift_date=lift_date, recorded_by=recorded_by,
        )
        active_events = await self.lift_repo.get_active_for_member(chitti.id, member.id)
        first_lift = min(active_events, key=lambda row: row.period_number)
        member = await self.member_repo.update(
            member, lifted=True,
            lifted_at=make_aware(datetime.combine(first_lift.lift_date, time.min)),
            lift_period=first_lift.period_number,
        )
        await self._recalculate_member_lift_schedule(chitti, member, first_lift.period_number,
                                                     from_period=period_number)
        await AuditService(self.session).log(
            user_id=recorded_by, action="CHITTI_LIFT_RECORDED", entity_type="CHITTI_LIFT",
            entity_id=event.id,
            new_value={"chitti_id": str(chitti.id), "member_id": str(member.id),
                       "period_number": period_number, "lift_date": str(lift_date)},
        )
        return {
            "id": str(event.id), "chitti_id": str(event.chitti_id),
            "member_id": str(event.member_id), "period_number": event.period_number,
            "lift_date": str(event.lift_date), "recorded_by": str(event.recorded_by) if event.recorded_by else None,
            "reversed_at": None,
        }

    async def reverse_lift(
        self, chitti_id: UUID, lift_id: UUID, *, reason: str, reversed_by: Optional[UUID]
    ) -> dict:
        chitti = await self.chitti_repo.get_by_id_for_update(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        event = await self.lift_repo.get_by_id_for_update(lift_id)
        if not event or event.chitti_id != chitti.id:
            raise NotFoundException("Chitti lift event", lift_id)
        if event.reversed_at:
            return {"id": str(event.id), "duplicate": True}
        from app.utils.timezone import now_ist
        await self.lift_repo.update(
            event, reversed_at=now_ist(), reversed_by=reversed_by, reversal_reason=reason
        )
        member = await self.member_repo.get_by_id_for_update(event.member_id)
        remaining_lifts = await self.lift_repo.get_active_for_member(chitti.id, member.id)
        first_lift = min(remaining_lifts, key=lambda row: row.period_number) if remaining_lifts else None
        await self.member_repo.update(
            member,
            lifted=first_lift is not None,
            lifted_at=make_aware(datetime.combine(first_lift.lift_date, time.min)) if first_lift else None,
            lift_period=first_lift.period_number if first_lift else None,
        )
        if not first_lift:
            member.lifted_at = None
            member.lift_period = None
        await self._recalculate_member_lift_schedule(
            chitti, member, first_lift.period_number if first_lift else None,
            from_period=min(event.period_number, first_lift.period_number) if first_lift else event.period_number,
        )
        await AuditService(self.session).log(
            user_id=reversed_by, action="CHITTI_LIFT_REVERSED", entity_type="CHITTI_LIFT",
            entity_id=event.id,
            previous_value={"period_number": event.period_number, "member_id": str(member.id)},
            new_value={"reversal_reason": reason},
        )
        return {"id": str(event.id), "reversed_at": str(event.reversed_at), "duplicate": False}

    async def _recalculate_member_lift_schedule(
        self, chitti, member, lift_period: Optional[int], *, from_period: int
    ) -> None:
        snapshot = chitti.plan_snapshot or {}
        engine = ChittiCalculationEngine(snapshot)
        duration = int(snapshot.get("duration", 0))
        total_value = Decimal(str(snapshot.get("total_value", 0)))
        member_count = int(snapshot.get("member_count", chitti.member_count))
        contributions = await self.contribution_repo.get_by_member_id(member.id)
        for row in contributions:
            if row.period_number < from_period:
                continue
            row = await self.contribution_repo.get_by_chitti_member_period_for_update(
                chitti.id, member.id, row.period_number
            )
            if not row:
                continue
            if hasattr(engine.contribution_strategy, "calculate_installment_for_member"):
                expected = engine.contribution_strategy.calculate_installment_for_member(
                    row.period_number, duration, total_value, member_count, lift_period
                )
            else:
                expected = engine.get_contribution_for_period(row.period_number)
            remaining = max(expected - row.paid_amount, Decimal("0"))
            status = "PAID" if remaining == 0 else (
                "PARTIALLY_PAID" if row.paid_amount > 0 else "UPCOMING"
            )
            await self.contribution_repo.update(
                row, expected_amount=expected, remaining_amount=remaining, status=status
            )
        await self._sync_period_schedules_from_contributions(chitti)
        await self._refresh_member_financials(chitti, member)

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
        idempotency_key: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> dict:
        chitti = await self.chitti_repo.get_by_id_for_update(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)

        member = await self.member_repo.get_by_id(UUID(member_id))
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)

        snapshot = chitti.plan_snapshot or {}
        duration = int(snapshot.get("duration", 0))
        if period_number < 1 or period_number > duration:
            raise BadRequestException("Payout period is outside the Chitti schedule.")

        money_values = (gross_payout, discount_amount, fee_amount, net_payout)
        if any(not value.is_finite() for value in money_values):
            raise BadRequestException("Payout amounts must be finite.")
        if any(value < Decimal("0") for value in money_values):
            raise BadRequestException("Payout amounts cannot be negative.")

        cents = Decimal("0.01")
        gross_payout = gross_payout.quantize(cents, rounding=ROUND_HALF_UP)
        discount_amount = discount_amount.quantize(cents, rounding=ROUND_HALF_UP)
        fee_amount = fee_amount.quantize(cents, rounding=ROUND_HALF_UP)
        net_payout = net_payout.quantize(cents, rounding=ROUND_HALF_UP)
        if net_payout != gross_payout - discount_amount - fee_amount:
            raise BadRequestException(
                "Net payout must equal gross payout minus discount and fee.",
                error_code="PAYOUT_AMOUNT_MISMATCH",
            )

        period_schedule = await self.schedule_repo.get_by_period_for_update(
            chitti.id, period_number
        )
        if not period_schedule:
            raise BadRequestException(
                "Payout period schedule is missing.",
                error_code="PAYOUT_PERIOD_SCHEDULE_MISSING",
            )

        existing_payout = await self.payout_repo.get_by_chitti_member_period_for_update(
            chitti.id, member.id, period_number
        )
        if existing_payout:
            if (
                existing_payout.gross_payout == gross_payout
                and existing_payout.discount_amount == discount_amount
                and existing_payout.fee_amount == fee_amount
                and existing_payout.net_payout == net_payout
                and existing_payout.payout_method == payout_method
            ):
                return {
                    "id": str(existing_payout.id),
                    "gross_payout": existing_payout.gross_payout,
                    "net_payout": existing_payout.net_payout,
                    "status": existing_payout.status,
                    "duplicate": True,
                }
            raise ConflictException(
                "A payout is already recorded for this member and period.",
                error_code="DUPLICATE_PAYOUT",
            )

        if idempotency_key:
            key = idempotency_key
        else:
            import hashlib
            canonical = (
                f"{chitti.id}|{member.id}|{period_number}|{gross_payout}"
                f"|{discount_amount}|{fee_amount}|{net_payout}|{payout_method}"
            )
            key = f"payout-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        existing_ledger = await self.txn_repo.get_by_idempotency_key(key)
        if existing_ledger:
            if (
                existing_ledger.chitti_id == chitti.id
                and existing_ledger.member_id == member.id
                and existing_ledger.period_number == period_number
                and existing_ledger.amount == net_payout
                and existing_ledger.payment_method == payout_method
                and existing_ledger.transaction_type == "PAYOUT"
            ):
                payout = await self.payout_repo.get_by_chitti_member_period_for_update(
                    chitti.id, member.id, period_number
                )
                if payout:
                    return {
                        "id": str(payout.id),
                        "gross_payout": payout.gross_payout,
                        "net_payout": payout.net_payout,
                        "status": payout.status,
                        "duplicate": True,
                    }
            raise ConflictException(
                "This payout idempotency key was already used for different payout details.",
                error_code="PAYOUT_IDEMPOTENCY_KEY_REUSED",
            )

        from app.utils.timezone import now_ist
        paid_at = now_ist()

        # Record the ledger first, then link the payout to that exact row.
        ledger = await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="PAYOUT",
            member_id=member.id,
            amount=net_payout,
            payment_method=payout_method,
            period_number=period_number,
            idempotency_key=key,
            created_by=created_by,
        )

        payout = await self.payout_repo.create(
            chitti_id=chitti.id,
            member_id=member.id,
            ledger_transaction_id=ledger.id,
            period_number=period_number,
            gross_payout=gross_payout,
            discount_amount=discount_amount,
            fee_amount=fee_amount,
            net_payout=net_payout,
            payout_method=payout_method,
            paid_at=paid_at,
            status="PAID",
        )

        # Update period schedule
        await self.schedule_repo.update(
            period_schedule,
            actual_payout=period_schedule.actual_payout + net_payout,
        )

        await AuditService(self.session).log(
            user_id=created_by,
            action="CHITTI_PAYOUT_RECORDED",
            entity_type="chitti_payout",
            entity_id=payout.id,
            new_value={
                "chitti_id": str(chitti.id),
                "member_id": str(member.id),
                "ledger_transaction_id": str(ledger.id),
                "payout_id": str(payout.id),
                "period_number": period_number,
                "gross_payout": str(gross_payout),
                "discount_amount": str(discount_amount),
                "fee_amount": str(fee_amount),
                "net_payout": str(net_payout),
                "payout_method": payout_method,
            },
        )

        return {
            "id": str(payout.id),
            "gross_payout": payout.gross_payout,
            "net_payout": payout.net_payout,
            "status": payout.status,
            "duplicate": False,
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
            effective_schedules = await self._effective_schedule_rows(chitti, schedules)
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
                (s for s in effective_schedules if s["status"] != "COMPLETED"), None
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
                "current_period": self._completed_period_progress(effective_schedules),
                "total_periods": chitti.plan_snapshot.get("duration", 0),
                "total_value": self._money(chitti.total_value),
                "expected_collection": self._money(totals["expected"]),
                "actual_collection": self._money(totals["collected"]),
                "pending_collection": self._money(totals["pending"]),
                "unallocated_credit": self._money(totals["unallocated_credit"]),
                "financials_source": totals["source"],
                "next_due_date": next_period["due_date"] if next_period else None,
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
        effective_schedules = await self._effective_schedule_rows(chitti, schedules)
        payouts = await self.payout_repo.get_by_chitti_id(chitti.id)
        totals = await self._financial_totals(chitti, schedules=schedules)
        activation = await self.activation_status(chitti)

        total_payouts = sum(
            (self._decimal(p.net_payout) for p in payouts if p.status == "PAID"),
            Decimal("0"),
        )

        next_period = next(
            (s for s in effective_schedules if s["status"] != "COMPLETED"), None
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
            "current_period": self._completed_period_progress(effective_schedules),
            "total_periods": chitti.plan_snapshot.get("duration", 0),
            "total_value": self._money(chitti.total_value),
            "expected_collection": self._money(totals["expected"]),
            "actual_collection": self._money(totals["collected"]),
            "pending_collection": self._money(totals["pending"]),
            "unallocated_credit": self._money(totals["unallocated_credit"]),
            "financials_source": totals["source"],
            "total_payouts": self._money(total_payouts),
            "outstanding": self._money(totals["pending"]),
            "activation": activation,
            "next_due_date": next_period["due_date"] if next_period else None,
            "next_payout_date": str(next_payout.paid_at) if next_payout else None,
        }

    # ===========================================================================
    # Explicit cross-module read interface
    # ===========================================================================

    async def get_effective_contribution_values(self, chitti, contributions=None) -> dict:
        """Public, read-only view of a Chitti group's effective contribution values.

        Other modules (for example the consolidated Payments collection screen)
        must use this method instead of reaching into private Chitti helpers or
        recomputing Chitti rules themselves. This method never mutates Chitti
        records; it only projects values owned by the Chitti module.
        """
        return await self._effective_contribution_values(chitti, contributions)

    # ===========================================================================
    # Helpers
    # ===========================================================================

    async def _effective_contribution_values(self, chitti, contributions=None) -> dict:
        """Use confirmed lift events as the source for lift-based expectations."""
        contributions = contributions or await self.contribution_repo.get_by_chitti_id(chitti.id)
        members = {member.id: member for member in await self.member_repo.get_by_chitti_id(chitti.id)}
        lifts = await self.lift_repo.get_by_chitti_id(chitti.id)
        from app.services.chitti_financial_values import effective_contribution_values
        return effective_contribution_values(
            chitti,
            members.values(),
            lifts,
            contributions,
        )

    @staticmethod
    def _unallocated_credit_by_member(allocations) -> dict[UUID, Decimal]:
        credits: dict[UUID, Decimal] = {}
        for allocation in allocations:
            if allocation.allocation_type == "CREDIT":
                credits[allocation.member_id] = (
                    credits.get(allocation.member_id, Decimal("0"))
                    + Decimal(str(allocation.amount))
                )
        invalid = {member_id: amount for member_id, amount in credits.items() if amount < 0}
        if invalid:
            raise RuntimeError("Chitti payment allocation history contains negative member credit.")
        return {member_id: amount for member_id, amount in credits.items() if amount > 0}

    @classmethod
    def _unallocated_credit(cls, allocations) -> Decimal:
        return sum(
            (
                cls._decimal(allocation.amount)
                for allocation in allocations
                if allocation.allocation_type == "CREDIT"
            ),
            Decimal("0"),
        )

    async def _refresh_member_financials(self, chitti, member) -> None:
        contributions = await self.contribution_repo.get_by_member_id(member.id)
        effective = await self._effective_contribution_values(chitti, contributions)
        allocations = await self.allocation_repo.get_by_member_id(chitti.id, member.id)
        credit = self._unallocated_credit(allocations)
        expected = sum(
            (effective[row.id]["expected"] for row in contributions),
            Decimal("0"),
        )
        allocated = sum((self._decimal(row.paid_amount) for row in contributions), Decimal("0"))
        outstanding = sum(
            (effective[row.id]["remaining"] for row in contributions),
            Decimal("0"),
        )
        # total_paid_amount reports allocated contributions only; available credit
        # and unresolved excess are shown separately instead of inflating it.
        await self.member_repo.update(
            member,
            total_expected_amount=expected,
            total_paid_amount=allocated,
            outstanding_amount=outstanding,
        )

    async def _refunded_amount(self, receipt_id: UUID) -> Decimal:
        """Cash already refunded against one receipt, from its own ledger legs."""
        allocations = await self.allocation_repo.get_by_source_transaction_id(receipt_id)
        if not allocations:
            return Decimal("0")
        transactions = await self.txn_repo.get_by_chitti_id(allocations[0].chitti_id)
        refund_ids = {row.id for row in transactions if row.transaction_type == "REFUND"}
        total = sum(
            (
                -self._decimal(allocation.amount)
                for allocation in allocations
                if allocation.event_transaction_id in refund_ids
            ),
            Decimal("0"),
        )
        return max(total, Decimal("0"))

    async def _effective_schedule_rows(self, chitti, schedules=None) -> list[dict]:
        """Read period totals/status from member contribution rows when available.

        This also repairs stale legacy display states without rewriting saved
        financial rows merely to render the UI.
        """
        schedules = schedules or await self.schedule_repo.get_by_chitti_id(chitti.id)
        contributions = await self.contribution_repo.get_by_chitti_id(chitti.id)
        effective_values = await self._effective_contribution_values(chitti, contributions)
        aggregates: dict[int, dict[str, Decimal]] = {}
        for contribution in contributions:
            entry = aggregates.setdefault(
                contribution.period_number,
                {"expected": Decimal("0"), "paid": Decimal("0")},
            )
            values = effective_values[contribution.id]
            entry["expected"] += values["expected"]
            entry["paid"] += values["paid"]

        effective = []
        today = today_ist()
        plan_snapshot = chitti.plan_snapshot or {}
        payout_rules = plan_snapshot.get("payout_rules", {}) or {}
        payout_type = payout_rules.get("type", "SCHEDULED")
        scheduled_payouts_available = payout_type in ("SCHEDULED", "CUSTOM")
        payout_engine = ChittiCalculationEngine(plan_snapshot) if scheduled_payouts_available else None
        for schedule in schedules:
            values = aggregates.get(schedule.period_number)
            expected = values["expected"] if values else self._decimal(schedule.expected_collection)
            paid = values["paid"] if values else self._decimal(schedule.actual_collection)
            pending = max(expected - paid, Decimal("0"))
            if paid > 0 and pending == 0:
                status = "COMPLETED"
            elif paid > 0:
                status = "PARTIALLY_PAID"
            elif schedule.due_date < today:
                status = "OVERDUE"
            elif schedule.due_date == today:
                status = "DUE"
            else:
                status = "UPCOMING"

            expected_payout = self._decimal(schedule.expected_payout)
            expected_payout_fee = Decimal("0")
            scheduled_member_number = None
            if payout_engine is not None:
                payout_projection = payout_engine.get_payout_for_period(
                    schedule.period_number,
                    expected,
                    chitti.member_count,
                )
                scheduled_member_number = payout_projection.get("member_number")
                expected_payout_fee = self._decimal(payout_projection.get("fee_amount"))
                # Recompute the projection from the immutable saved rule and
                # period collection so stale legacy zeros (or old estimates)
                # cannot hide the expected payout. This is read-only: no payout
                # transaction or persisted balance is created here.
                expected_payout = self._decimal(payout_projection.get("net_payout"))
            effective.append({
                "id": str(schedule.id),
                "chitti_id": str(schedule.chitti_id),
                "period_number": schedule.period_number,
                "due_date": str(schedule.due_date),
                "expected_collection": self._money(expected),
                "actual_collection": self._money(paid),
                "pending_collection": self._money(pending),
                "expected_payout": self._money(expected_payout),
                "expected_payout_fee": self._money(expected_payout_fee),
                "scheduled_member_number": scheduled_member_number,
                "payout_schedule_available": scheduled_payouts_available,
                "actual_payout": self._money(schedule.actual_payout),
                "status": status,
            })
        return effective

    @staticmethod
    def _completed_period_progress(schedule_rows: list[dict]) -> int:
        """Count completed periods from period 1 without skipping an unpaid gap."""
        completed = 0
        for row in schedule_rows:
            if row["period_number"] != completed + 1 or row["status"] != "COMPLETED":
                break
            completed = row["period_number"]
        return completed

    async def _financial_totals(self, chitti, schedules=None) -> dict:
        """Money totals for a chitti from one consistent source.

        Contribution rows are authoritative because record_contribution writes
        them and refreshes member aggregates from them. Period schedules are
        only a fallback for chittis created before any contribution row existed,
        and that fallback is logged rather than hidden.
        """
        contributions = await self.contribution_repo.get_by_chitti_id(chitti.id)
        allocations = await self.allocation_repo.get_by_chitti_id(chitti.id)
        credits_by_member = self._unallocated_credit_by_member(allocations)
        unallocated_credit = sum(credits_by_member.values(), Decimal("0"))
        if contributions:
            effective_values = await self._effective_contribution_values(chitti, contributions)
            allocated = sum(
                (self._decimal(c.paid_amount) for c in contributions),
                Decimal("0"),
            )
            return {
                "expected": sum(
                    (self._decimal(effective_values[c.id]["expected"]) for c in contributions), Decimal("0")
                ),
                "collected": allocated,
                "pending": sum(
                    (self._decimal(effective_values[c.id]["remaining"]) for c in contributions), Decimal("0")
                ),
                "unallocated_credit": unallocated_credit,
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
                    (
                        max(
                            self._decimal(s.expected_collection)
                            - self._decimal(s.actual_collection),
                            Decimal("0"),
                        )
                        for s in schedules
                    ),
                    Decimal("0"),
                ),
                "unallocated_credit": unallocated_credit,
                "source": "schedule",
            }

        # Not started yet: no member dues have been generated, so reporting the
        # plan-wide schedule total here would overstate pending money.
        return {
            "expected": Decimal("0"),
            "collected": Decimal("0"),
            "pending": Decimal("0"),
            "unallocated_credit": unallocated_credit,
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
                    member_lift_period=None,
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

        effective_values = await self._effective_contribution_values(chitti, contributions)

        aggregates: dict[int, dict] = {}
        for con in contributions:
            entry = aggregates.setdefault(
                con.period_number,
                {
                    "expected": Decimal("0"),
                    "paid": Decimal("0"),
                    "remaining": Decimal("0"),
                },
            )
            values = effective_values[con.id]
            entry["expected"] += values["expected"]
            entry["paid"] += values["paid"]
            entry["remaining"] += values["remaining"]

        schedule_rows = []
        today = today_ist()
        schedules = await self.schedule_repo.get_by_chitti_id(chitti.id)
        for schedule in schedules:
            schedule = await self.schedule_repo.get_by_period_for_update(
                chitti.id, schedule.period_number
            )
            if not schedule:
                continue
            entry = aggregates.get(schedule.period_number)
            if entry is None:
                continue
            expected = entry["expected"]
            paid = entry["paid"]
            pending = entry["remaining"]
            if expected > 0 and pending == 0:
                status = "COMPLETED"
            elif paid > 0:
                # ACTIVE is the persisted enum value for a period with partial
                # collection; the read model exposes PARTIALLY_PAID explicitly.
                status = "ACTIVE"
            elif schedule.due_date < today:
                status = "OVERDUE"
            elif schedule.due_date == today:
                # ACTIVE is the persisted enum value; the read model maps it
                # to the clearer DUE label for an unpaid period due today.
                status = "ACTIVE"
            else:
                status = "UPCOMING"
            await self.schedule_repo.update(
                schedule,
                expected_collection=expected,
                actual_collection=paid,
                pending_collection=pending,
                status=status,
            )
            schedule_rows.append({"period_number": schedule.period_number, "status": status})
        await self.chitti_repo.update(
            chitti,
            current_period=self._completed_period_progress(schedule_rows),
        )

    def _build_plan_snapshot(self, plan: ChittiPlan) -> dict:
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
        unallocated_credit=Decimal("0"),
        unresolved_excess=Decimal("0"),
        outstanding=None,
    ) -> dict:
        if outstanding is None:
            outstanding = max(
                self._decimal(total_expected) - self._decimal(total_paid),
                Decimal("0"),
            )
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
            "alias": getattr(member, "alias", None),
            "customer_code": customer.customer_code if customer else None,
            "mobile_number": customer.mobile_number if customer else None,
            "member_number": member.member_number,
            "payout_order": member.payout_order,
            "status": member.status,
            "joined_at": str(member.joined_at),
            "total_expected": self._money(total_expected),
            "total_paid": self._money(total_paid),
            "outstanding": self._money(outstanding),
            "unallocated_credit": self._money(unallocated_credit),
            "unresolved_excess": self._money(unresolved_excess),
        }
