"""
Agreement Service — handles member enrollment, agreement generation, printing, confirmation.

Workflow:
1. Add Member → PENDING_AGREEMENT
2. Generate Agreement → AGREEMENT_GENERATED
3. Print Agreement → AGREEMENT_PRINTED
4. Confirm Agreement → ACTIVE
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.repositories.agreement_repo import ChittiAgreementRepository
from app.repositories.chitti_repo import (
    ChittiContributionRepository,
    ChittiMemberRepository,
    ChittiRepository,
)
from app.repositories.customer_repo import CustomerRepository
from app.services.chitti_calculation import ChittiCalculationEngine
from app.utils.timezone import now_ist, today_ist


# Valid status transitions for member enrollment
MEMBER_STATUS_TRANSITIONS = {
    "PENDING_AGREEMENT": ["AGREEMENT_GENERATED", "CANCELLED"],
    "AGREEMENT_GENERATED": ["AGREEMENT_PRINTED", "CANCELLED"],
    "AGREEMENT_PRINTED": ["ACTIVE", "CANCELLED"],
    "ACTIVE": ["COMPLETED", "LEFT"],
    "REJECTED": [],
    "CANCELLED": [],
    "COMPLETED": [],
    "LEFT": [],
    "REPLACED": [],
}


class AgreementService:
    """Handles member enrollment and agreement workflow."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.agreement_repo = ChittiAgreementRepository(session)
        self.chitti_repo = ChittiRepository(session)
        self.member_repo = ChittiMemberRepository(session)
        self.contribution_repo = ChittiContributionRepository(session)
        self.customer_repo = CustomerRepository(session)

    # ===========================================================================
    # Add Member
    # ===========================================================================

    async def add_member(
        self,
        chitti_id: UUID,
        *,
        customer_id: str,
        payout_order: Optional[int] = None,
        created_by: Optional[UUID] = None,
    ) -> dict:
        """Add a customer to a chitti as PENDING_AGREEMENT member."""
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        if chitti.status not in ("DRAFT", "UPCOMING"):
            raise BadRequestException("Can only add members to DRAFT or UPCOMING chittis.")

        # Validate customer
        customer = await self.customer_repo.get_by_id(UUID(customer_id))
        if not customer:
            raise NotFoundException("Customer", customer_id)

        # Check duplicate membership
        existing = await self.member_repo.get_by_chitti_and_customer(
            chitti.id, UUID(customer_id)
        )
        if existing and existing.status not in ("CANCELLED", "REJECTED"):
            raise ConflictException(
                f"{customer.full_name} is already a member of this chitti."
            )

        # Check capacity
        active_count = await self.member_repo.count_active(chitti.id)
        if active_count >= chitti.member_count:
            raise BadRequestException(
                f"Chitti is full. Maximum {chitti.member_count} members allowed."
            )

        # Determine member number
        max_num = await self.member_repo.max_member_number(chitti.id)
        member_number = max_num + 1

        member = await self.member_repo.create(
            chitti_id=chitti.id,
            customer_id=UUID(customer_id),
            member_number=member_number,
            payout_order=payout_order or member_number,
            status="PENDING_AGREEMENT",
            total_expected_amount=Decimal("0"),
            total_paid_amount=Decimal("0"),
            outstanding_amount=Decimal("0"),
            lifted=False,
        )

        return self._member_to_dict(member, customer)

    # ===========================================================================
    # Generate Agreement
    # ===========================================================================

    async def generate_agreement(
        self,
        member_id: UUID,
        *,
        created_by: Optional[UUID] = None,
    ) -> dict:
        """Generate agreement for a PENDING_AGREEMENT member.
        
        Creates a full snapshot of terms at enrollment time.
        """
        member = await self.member_repo.get_by_id(member_id)
        if not member:
            raise NotFoundException("Chitti Member", member_id)
        if member.status != "PENDING_AGREEMENT":
            raise BadRequestException(
                f"Cannot generate agreement for member with status {member.status}."
            )

        chitti = await self.chitti_repo.get_by_id(member.chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", member.chitti_id)

        customer = await self.customer_repo.get_by_id(member.customer_id)
        if not customer:
            raise NotFoundException("Customer", member.customer_id)

        # Build the agreement snapshot
        snapshot = self._build_agreement_snapshot(chitti, member, customer)

        # Generate agreement number
        agreement_number = await self._generate_agreement_number()

        now = now_ist()

        agreement = await self.agreement_repo.create(
            agreement_number=agreement_number,
            chitti_id=chitti.id,
            chitti_member_id=member.id,
            customer_id=customer.id,
            agreement_date=today_ist(),
            agreement_status="GENERATED",
            agreement_snapshot=snapshot,
            generated_at=now,
        )

        # Update member status and link agreement
        await self.member_repo.update(
            member,
            status="AGREEMENT_GENERATED",
            agreement_id=agreement.id,
        )
        await self.session.commit()

        return self._agreement_to_dict(agreement)

    # ===========================================================================
    # Print Agreement
    # ===========================================================================

    async def print_agreement(
        self,
        agreement_id: UUID,
    ) -> dict:
        """Record that the agreement was printed."""
        agreement = await self.agreement_repo.get_by_id(agreement_id)
        if not agreement:
            raise NotFoundException("Agreement", agreement_id)
        if agreement.agreement_status not in ("GENERATED", "PRINTED"):
            raise BadRequestException(
                f"Cannot print agreement with status {agreement.agreement_status}."
            )

        now = now_ist()
        agreement = await self.agreement_repo.update(
            agreement,
            agreement_status="PRINTED",
            printed_at=now if not agreement.printed_at else agreement.printed_at,
            print_count=agreement.print_count + 1,
        )
        await self.session.refresh(agreement)

        # Update member status
        member = await self.member_repo.get_by_id(agreement.chitti_member_id)
        if member and member.status == "AGREEMENT_GENERATED":
            await self.member_repo.update(member, status="AGREEMENT_PRINTED")
        await self.session.commit()

        return self._agreement_to_dict(agreement)

    # ===========================================================================
    # Confirm Agreement
    # ===========================================================================

    async def confirm_agreement(
        self,
        agreement_id: UUID,
    ) -> dict:
        """Confirm the agreement after physical signature. Activates the member."""
        agreement = await self.agreement_repo.get_by_id(agreement_id)
        if not agreement:
            raise NotFoundException("Agreement", agreement_id)
        if agreement.agreement_status != "PRINTED":
            raise BadRequestException(
                f"Cannot confirm agreement with status {agreement.agreement_status}. "
                "Agreement must be printed first."
            )

        now = now_ist()
        agreement = await self.agreement_repo.update(
            agreement,
            agreement_status="CONFIRMED",
            confirmed_at=now,
        )
        await self.session.refresh(agreement)

        # Activate the member
        member = await self.member_repo.get_by_id(agreement.chitti_member_id)
        if member:
            chitti = await self.chitti_repo.get_by_id(member.chitti_id)
            contributions = await self.contribution_repo.get_by_member_id(member.id)

            # Materialise the contribution schedule at activation. Agreement-enrolled
            # members previously had no contribution rows, so no payment could ever
            # be recorded against them and analytics showed zero dues.
            if not contributions and chitti:
                engine = ChittiCalculationEngine(chitti.plan_snapshot or {})
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

            if contributions:
                total_expected = sum(
                    (c.expected_amount for c in contributions), Decimal("0")
                )
            else:
                total_expected = self._calculate_total_expected(
                    agreement.agreement_snapshot
                )
            total_paid = sum((c.paid_amount for c in contributions), Decimal("0"))

            await self.member_repo.update(
                member,
                status="ACTIVE",
                total_expected_amount=total_expected,
                total_paid_amount=total_paid,
                outstanding_amount=max(total_expected - total_paid, Decimal("0")),
            )
        await self.session.commit()

        return self._agreement_to_dict(agreement)

    # ===========================================================================
    # Get Agreement
    # ===========================================================================

    async def get_agreement(self, agreement_id: UUID) -> dict:
        agreement = await self.agreement_repo.get_by_id(agreement_id)
        if not agreement:
            raise NotFoundException("Agreement", agreement_id)
        return self._agreement_to_dict(agreement)

    async def get_agreement_by_member(self, member_id: UUID) -> Optional[dict]:
        agreement = await self.agreement_repo.get_by_member_id(member_id)
        if not agreement:
            return None
        return self._agreement_to_dict(agreement)

    # ===========================================================================
    # Cancel Member
    # ===========================================================================

    async def cancel_member(
        self,
        member_id: UUID,
        *,
        reason: str = "",
    ) -> dict:
        """Cancel a member enrollment."""
        member = await self.member_repo.get_by_id(member_id)
        if not member:
            raise NotFoundException("Member", member_id)
        if member.status in ("ACTIVE", "COMPLETED", "LEFT"):
            raise BadRequestException(
                f"Cannot cancel member with status {member.status}."
            )

        # Cancel any existing agreement
        if member.agreement_id:
            agreement = await self.agreement_repo.get_by_id(member.agreement_id)
            if agreement and agreement.agreement_status not in ("CONFIRMED", "CANCELLED"):
                await self.agreement_repo.update(
                    agreement,
                    agreement_status="CANCELLED",
                    cancelled_at=now_ist(),
                    cancellation_reason=reason,
                )

        await self.member_repo.update(member, status="CANCELLED")
        await self.session.commit()
        return {"message": "Member cancelled."}

    # ===========================================================================
    # Helpers
    # ===========================================================================

    def _build_agreement_snapshot(self, chitti, member, customer) -> dict:
        """Build a complete snapshot of all terms at enrollment time."""
        snapshot = chitti.plan_snapshot or {}

        # Customer snapshot
        customer_snapshot = {
            "full_name": customer.full_name,
            "customer_code": customer.customer_code,
            "mobile_number": customer.mobile_number,
            "alternate_mobile": customer.alternate_mobile,
            "email": customer.email,
            "date_of_birth": str(customer.date_of_birth) if customer.date_of_birth else None,
            "gender": customer.gender,
            "address": customer.address,
            "city": customer.city,
            "state": customer.state,
            "pincode": customer.pincode,
            "pan_number": customer.pan_number,
            "aadhar_number": customer.aadhar_number,
            "occupation": customer.occupation,
            "nominee_name": customer.nominee_name,
            "nominee_phone": customer.nominee_phone,
            "nominee_relation": customer.nominee_relation,
        }

        # Chitti snapshot
        chitti_snapshot = {
            "chitti_code": chitti.chitti_code,
            "name": chitti.name,
            "branch": chitti.branch,
            "start_date": str(chitti.start_date),
            "end_date": str(chitti.end_date),
            "member_count": chitti.member_count,
            "total_value": float(chitti.total_value),
            "status": chitti.status,
        }

        return {
            "customer": customer_snapshot,
            "chitti": chitti_snapshot,
            "plan": snapshot,
            "member_number": member.member_number,
            "payout_order": member.payout_order,
            "agreement_date": str(today_ist()),
        }

    def _calculate_total_expected(self, snapshot: dict) -> Decimal:
        """Calculate total expected contribution from snapshot."""
        plan = snapshot.get("plan", {})
        contrib_rules = plan.get("contribution_rules", {})
        rule_type = contrib_rules.get("type", "FIXED")
        duration = plan.get("duration", 1)
        member_count = plan.get("member_count", 1)
        total_value = Decimal(str(plan.get("total_value", 0)))

        if rule_type == "FIXED":
            installment = Decimal(str(contrib_rules.get("installment_amount", 0)))
            return installment * Decimal(str(duration))
        elif rule_type == "LIFT_BASED":
            # For lift-based, use post-lift amount as the standard
            post = Decimal(str(contrib_rules.get("post_lift_amount", 0)))
            pre = Decimal(str(contrib_rules.get("pre_lift_amount", 0)))
            # Approximate: (duration-1) * post + 1 * pre (for last member)
            return (post * Decimal(str(duration - 1))) + pre
        elif rule_type == "CUSTOM":
            schedule = contrib_rules.get("schedule", [])
            return sum(Decimal(str(s.get("amount", 0))) for s in schedule)
        else:
            # Default: use total_value / member_count * duration
            return (total_value / Decimal(str(member_count))) * Decimal(str(duration))

    async def _generate_agreement_number(self) -> str:
        """Generate unique agreement number: AGR-YYYY-NNNNNN"""
        year = today_ist().year
        count = await self.agreement_repo.count_by_chitti(UUID("00000000-0000-0000-0000-000000000000"))
        # Use a simple counter based on total agreements
        from sqlalchemy import func, select
        from app.models.chitti import ChittiAgreement
        result = await self.session.execute(
            select(func.count()).select_from(ChittiAgreement)
        )
        total = result.scalar() or 0
        return f"AGR-{year}-{total + 1:06d}"

    def _member_to_dict(self, member, customer=None) -> dict:
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
            "agreement_id": str(member.agreement_id) if member.agreement_id else None,
            "total_expected_amount": float(member.total_expected_amount) if member.total_expected_amount else 0,
            "total_paid_amount": float(member.total_paid_amount) if member.total_paid_amount else 0,
            "outstanding_amount": float(member.outstanding_amount) if member.outstanding_amount else 0,
            "lifted": member.lifted,
            "lifted_at": str(member.lifted_at) if member.lifted_at else None,
            "lift_period": member.lift_period,
            "joined_at": str(member.joined_at),
        }

    def _agreement_to_dict(self, agreement) -> dict:
        snapshot = agreement.agreement_snapshot or {}
        return {
            "id": str(agreement.id),
            "agreement_number": agreement.agreement_number,
            "chitti_id": str(agreement.chitti_id),
            "chitti_member_id": str(agreement.chitti_member_id),
            "customer_id": str(agreement.customer_id),
            "agreement_date": str(agreement.agreement_date),
            "agreement_status": agreement.agreement_status,
            "agreement_snapshot": snapshot,
            "generated_at": str(agreement.generated_at) if agreement.generated_at else None,
            "printed_at": str(agreement.printed_at) if agreement.printed_at else None,
            "print_count": agreement.print_count,
            "confirmed_at": str(agreement.confirmed_at) if agreement.confirmed_at else None,
            "cancelled_at": str(agreement.cancelled_at) if agreement.cancelled_at else None,
            "cancellation_reason": agreement.cancellation_reason,
            "created_at": str(agreement.created_at),
            "updated_at": str(agreement.updated_at),
        }
