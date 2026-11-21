"""
Agreement Service — handles member enrollment, agreement generation, printing, confirmation.

Workflow:
1. Add Member → PENDING_AGREEMENT
2. Generate Agreement → AGREEMENT_GENERATED
3. Print Agreement → AGREEMENT_PRINTED
4. Confirm Agreement → ACTIVE
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.aliases import normalize_slot_alias
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from sqlalchemy.exc import IntegrityError
from app.repositories.agreement_repo import ChittiAgreementRepository
from app.repositories.chitti_repo import (
    ENROLLED_EXCLUDED_STATUSES,
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


def _normalize_alias(value: Optional[str], *, error_code: str = "INVALID_ALIAS") -> Optional[str]:
    """Compatibility wrapper around the shared alias normalizer."""
    return normalize_slot_alias(value, error_code=error_code)


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
        alias: Optional[str] = None,
    ) -> dict:
        """Add a customer to a chitti as PENDING_AGREEMENT member."""
        chitti = await self.chitti_repo.get_by_id_for_update(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        if chitti.status not in ("DRAFT", "UPCOMING"):
            raise BadRequestException("Can only add members to DRAFT or UPCOMING chittis.")

        # Validate customer
        customer = await self.customer_repo.get_by_id(UUID(customer_id))
        if not customer:
            raise NotFoundException("Customer", customer_id)

        # Multiple slots for the same customer are allowed. Every additional
        # slot must carry a unique alias so payments and agreements can be
        # attributed to one exact membership, never to the customer's main slot.
        normalized_alias = _normalize_alias(alias, error_code="INVALID_ALIAS")
        existing_slots = await self.member_repo.list_by_chitti_and_customer(
            chitti.id, UUID(customer_id)
        )
        enrolled_slots = [
            slot for slot in existing_slots
            if slot.status not in ENROLLED_EXCLUDED_STATUSES
        ]
        if enrolled_slots and not normalized_alias:
            raise BadRequestException(
                "This customer already has a slot in this Chitti. Enter a unique alias for the new slot.",
                error_code="ALIAS_REQUIRED",
                details={
                    "existing_slots": [
                        {
                            "member_id": str(slot.id),
                            "member_number": slot.member_number,
                            "alias": slot.alias,
                        }
                        for slot in enrolled_slots
                    ]
                },
            )
        if normalized_alias:
            existing_alias = await self.member_repo.get_by_chitti_and_alias(
                chitti.id, normalized_alias
            )
            if existing_alias:
                raise ConflictException(
                    "Alias already used in this Chitti.",
                    error_code="DUPLICATE_ALIAS",
                )

        # Capacity counts every member holding a place, not only ACTIVE ones —
        # pending-agreement members already occupy a slot.
        enrolled_count = await self.member_repo.count_enrolled(chitti.id)
        if enrolled_count >= chitti.member_count:
            raise BadRequestException(
                f"This Chitti is full. Maximum {chitti.member_count} members allowed.",
                error_code="CHITTI_FULL",
                details={
                    "chitti_id": str(chitti.id),
                    "member_capacity": chitti.member_count,
                    "enrolled_members": enrolled_count,
                    "available_slots": 0,
                },
            )

        max_num = await self.member_repo.max_member_number(chitti.id)
        member_number = max_num + 1

        try:
            member = await self.member_repo.create_with_savepoint(
                chitti_id=chitti.id,
                customer_id=UUID(customer_id),
                member_number=member_number,
                payout_order=payout_order if payout_order is not None else member_number,
                status="PENDING_AGREEMENT",
                total_expected_amount=Decimal("0"),
                total_paid_amount=Decimal("0"),
                outstanding_amount=Decimal("0"),
                lifted=False,
                alias=normalized_alias,
            )
        except IntegrityError as exc:
            # A racing enrollment can pass the pre-check; the unique index is
            # the final guard. Map its violation to the same structured 409.
            raise ConflictException(
                "Alias already used in this Chitti.",
                error_code="DUPLICATE_ALIAS",
            ) from exc

        from app.services.audit_service import AuditService
        await AuditService(self.session).log(
            user_id=created_by,
            action="CHITTI_MEMBER_ENROLLED",
            entity_type="chitti_member",
            entity_id=member.id,
            new_value={
                "chitti_id": str(chitti.id),
                "customer_id": str(customer.id),
                "member_number": member_number,
                "alias": normalized_alias,
                "status": "PENDING_AGREEMENT",
            },
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
        # Serialise concurrent generate calls for the same slot. The unique
        # constraint on chitti_member_id is the final guard if two processes
        # still race past the application check.
        member = await self.member_repo.get_by_id_for_update(member_id)
        if not member:
            raise NotFoundException("Chitti Member", member_id)
        if member.status != "PENDING_AGREEMENT":
            raise BadRequestException(
                f"Cannot generate agreement for member with status {member.status}."
            )
        if await self.agreement_repo.get_by_member_id(member_id):
            raise ConflictException(
                "An agreement already exists for this member.",
                error_code="DUPLICATE_AGREEMENT",
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

        try:
            agreement = await self.agreement_repo.create_with_savepoint(
                agreement_number=agreement_number,
                chitti_id=chitti.id,
                chitti_member_id=member.id,
                customer_id=customer.id,
                agreement_date=today_ist(),
                agreement_status="GENERATED",
                agreement_snapshot=snapshot,
                generated_at=now,
            )
        except IntegrityError as exc:
            # The status check above is not enough on its own: two separate
            # sessions can both pass it before either commits. The database
            # constraint decides the winner and this maps the loser to a
            # structured conflict rather than an opaque 500.
            raise ConflictException(
                "An agreement already exists for this member.",
                error_code="DUPLICATE_AGREEMENT",
            ) from exc

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
        *,
        created_by: Optional[UUID] = None,
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
                    member_lift_period=None,
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
        # Agreement confirmation activates this member only. Starting the
        # Chitti is a separate, explicit operation through the canonical
        # /start transition after the operator reviews activation readiness.
        chitti = await self.chitti_repo.get_by_id(member.chitti_id) if member else None
        chitti_status = chitti.status if chitti else None
        chitti_auto_started = False

        await self.session.commit()

        result = self._agreement_to_dict(agreement)
        result["chitti_status"] = chitti_status
        result["chitti_auto_started"] = chitti_auto_started
        return result

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
        created_by: Optional[UUID] = None,
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

        previous_status = member.status
        await self.member_repo.update(member, status="CANCELLED")

        from app.services.audit_service import AuditService
        await AuditService(self.session).log(
            user_id=created_by,
            action="CHITTI_MEMBER_CANCELLED",
            entity_type="chitti_member",
            entity_id=member.id,
            previous_value={"status": previous_status},
            new_value={"status": "CANCELLED", "reason": reason},
        )

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
            if contrib_rules.get("regular_amount") is not None:
                regular = Decimal(str(contrib_rules["regular_amount"]))
                surcharge = (total_value / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                member_number = int(snapshot.get("member_number") or member_count)
                payout_rules = plan.get("payout_rules", {})
                lift_period = member_number
                if payout_rules.get("type") == "CUSTOM":
                    lift_period = next(
                        (
                            int(entry["period"])
                            for entry in payout_rules.get("payout_schedule", [])
                            if int(entry.get("member_number", 0)) == member_number
                        ),
                        member_number,
                    )
                surcharge_periods = max(0, duration - lift_period)
                return regular * Decimal(str(duration)) + surcharge * Decimal(str(surcharge_periods))
            # Old agreements keep their captured legacy pre/post terms.
            post = Decimal(str(contrib_rules.get("post_lift_amount", 0)))
            pre = Decimal(str(contrib_rules.get("pre_lift_amount", 0)))
            return (post * Decimal(str(duration - 1))) + pre
        elif rule_type == "CUSTOM":
            schedule = contrib_rules.get("schedule", [])
            return sum(Decimal(str(s.get("amount", 0))) for s in schedule)
        else:
            # Default: use total_value / member_count * duration
            return (total_value / Decimal(str(member_count))) * Decimal(str(duration))

    async def _generate_agreement_number(self) -> str:
        """Generate a collision-resistant agreement number: AGR-YYYY-NNNNNNNNNNNN.

        A count-based suffix races when two agreements are created in different
        transactions; a random suffix keeps the number unique without taking
        another lock. The database unique constraint remains the final guard.
        """
        year = today_ist().year
        return f"AGR-{year}-{uuid4().int % 10**12:012d}"

    def _member_to_dict(self, member, customer=None) -> dict:
        return {
            "id": str(member.id),
            "chitti_id": str(member.chitti_id),
            "customer_id": str(member.customer_id),
            "customer_name": customer.full_name if customer else None,
            "customer_code": customer.customer_code if customer else None,
            "mobile_number": customer.mobile_number if customer else None,
            "alias": getattr(member, "alias", None),
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
