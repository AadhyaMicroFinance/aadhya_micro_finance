"""Operator-driven credit application, excess resolution and refunds.

Every method here is an explicit, audited operator action. Nothing in this
module runs automatically: recording a receipt, reversing a receipt or
recalculating a lift never creates, moves or applies credit.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.repositories.audit_repo import AuditLogRepository
from app.services.audit_service import AuditService
from app.services.chitti_service import ChittiService
from app.utils.timezone import today_ist


def _money(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


class ChittiCreditService:
    """Credit, excess, over-allocation and refund operations for one Chitti."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.base = ChittiService(session)
        self.chitti_repo = self.base.chitti_repo
        self.member_repo = self.base.member_repo
        self.contribution_repo = self.base.contribution_repo
        self.allocation_repo = self.base.allocation_repo
        self.txn_repo = self.base.txn_repo
        self.audit_repo = AuditLogRepository(session)
        self._decimal = self.base._decimal

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fingerprint(**values) -> str:
        payload = json.dumps(values, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def _lock_chitti(self, chitti_id: UUID):
        chitti = await self.chitti_repo.get_by_id_for_update(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        if chitti.status != "RUNNING":
            raise BadRequestException("Chitti is not in RUNNING status.")
        return chitti

    async def _lock_member(self, chitti, member_id) -> object:
        try:
            identifier = UUID(str(member_id))
        except (TypeError, ValueError):
            raise NotFoundException("Member", member_id)
        member = await self.member_repo.get_by_id_for_update(identifier)
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)
        return member

    async def _lock_receipt(self, chitti, receipt_id) -> object:
        try:
            identifier = UUID(str(receipt_id))
        except (TypeError, ValueError):
            raise NotFoundException("Chitti transaction", receipt_id)
        receipt = await self.txn_repo.get_by_id_for_update(identifier)
        if not receipt or receipt.chitti_id != chitti.id:
            raise NotFoundException("Chitti transaction", receipt_id)
        if receipt.transaction_type != "CONTRIBUTION":
            raise BadRequestException(
                "Only contribution receipts can fund credit, excess resolution "
                "or refunds.",
                error_code="RECEIPT_NOT_CONTRIBUTION",
            )
        return receipt

    async def _replay(self, key: str, fingerprint: str, action: str):
        existing = await self.txn_repo.get_by_idempotency_key(key)
        if not existing:
            return None
        rows = await self.audit_repo.get_by_entity("chitti_transaction", existing.id)
        row = next((item for item in rows if item.action == action), None)
        payload = (row.new_value or {}) if row else {}
        snapshot = payload.get("response_snapshot")
        if not row or not snapshot:
            raise ConflictException(
                "This idempotency key was already used and its stored result is "
                "unavailable.",
                error_code="IDEMPOTENCY_SNAPSHOT_MISSING",
            )
        if payload.get("request_fingerprint") != fingerprint:
            raise BadRequestException(
                "This idempotency key was already used for a different request.",
                error_code="IDEMPOTENCY_KEY_REUSED",
            )
        return {**snapshot, "audit_log_id": str(row.id), "duplicate": True}

    async def _audit(self, *, action, entity_id, user_id, fingerprint, response, extra=None, previous=None, ip_address=None, user_agent=None):
        new_value = {
            "request_fingerprint": fingerprint,
            "response_snapshot": response,
        }
        if extra:
            new_value.update(extra)
        row = await AuditService(self.session).log(
            user_id=user_id,
            action=action,
            entity_type="chitti_transaction",
            entity_id=entity_id,
            previous_value=previous,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.session.flush()
        return row

    def _credit_balances(self, allocations) -> dict[UUID, Decimal]:
        balances: dict[UUID, Decimal] = {}
        for allocation in allocations:
            if allocation.allocation_type == "CREDIT":
                balances[allocation.source_transaction_id] = (
                    balances.get(allocation.source_transaction_id, Decimal("0"))
                    + self._decimal(allocation.amount)
                )
        invalid = [value for value in balances.values() if value < 0]
        if invalid:
            raise RuntimeError(
                "Chitti payment allocation history contains negative member credit."
            )
        return balances

    def _unresolved_balances(self, allocations) -> dict[UUID, Decimal]:
        balances: dict[UUID, Decimal] = {}
        for allocation in allocations:
            if allocation.allocation_type == "UNRESOLVED":
                balances[allocation.source_transaction_id] = (
                    balances.get(allocation.source_transaction_id, Decimal("0"))
                    + self._decimal(allocation.amount)
                )
        return balances

    async def _save_contribution(self, chitti, contribution, new_paid, expected) -> None:
        remaining = max(expected - new_paid, Decimal("0"))
        status = (
            "PAID" if remaining == 0 and expected > 0
            else "PARTIALLY_PAID" if new_paid > 0
            else "UPCOMING"
        )
        await self.contribution_repo.update(
            contribution,
            expected_amount=expected,
            paid_amount=new_paid,
            remaining_amount=remaining,
            status=status,
        )

    # ------------------------------------------------------------------
    # Credit position
    # ------------------------------------------------------------------

    async def get_customer_credit(self, customer_id: UUID) -> dict:
        members = await self.member_repo.get_by_customer_id(customer_id)
        entries = []
        totals = {
            "available_credit": Decimal("0"),
            "unresolved_excess": Decimal("0"),
            "outstanding": Decimal("0"),
            "cash_received": Decimal("0"),
            "allocated": Decimal("0"),
            "refunded": Decimal("0"),
        }
        for member in members:
            chitti = await self.chitti_repo.get_by_id(member.chitti_id)
            if not chitti:
                continue
            allocations = await self.allocation_repo.get_by_member_id(
                chitti.id, member.id
            )
            contributions = await self.contribution_repo.get_by_member_id(member.id)
            effective = await self.base._effective_contribution_values(
                chitti, contributions
            )
            credit = sum(self._credit_balances(allocations).values(), Decimal("0"))
            unresolved = sum(
                self._unresolved_balances(allocations).values(), Decimal("0")
            )
            allocated = sum(
                (self._decimal(row.paid_amount) for row in contributions),
                Decimal("0"),
            )
            outstanding = sum(
                (self._decimal(effective[row.id]["remaining"]) for row in contributions),
                Decimal("0"),
            )
            receipts = await self.txn_repo.get_by_member_id(member.id)
            # A reversal is a ledger row of its own. Subtract its amount from
            # the original receipt instead of double-counting cash the customer
            # no longer has. Historical rows link the pair through
            # original_transaction_id.
            reversed_amounts: dict[UUID, Decimal] = {}
            for row in receipts:
                if row.transaction_type == "REVERSAL" and row.original_transaction_id:
                    reversed_amounts[row.original_transaction_id] = (
                        reversed_amounts.get(row.original_transaction_id, Decimal("0"))
                        + self._decimal(row.amount)
                    )
            cash_received = sum(
                (
                    max(
                        Decimal("0"),
                        self._decimal(row.amount)
                        - reversed_amounts.get(row.id, Decimal("0")),
                    )
                    for row in receipts
                    if row.transaction_type == "CONTRIBUTION"
                ),
                Decimal("0"),
            )
            refunded = sum(
                (
                    self._decimal(row.amount)
                    for row in receipts
                    if row.transaction_type == "REFUND"
                ),
                Decimal("0"),
            )
            entries.append({
                "chitti_id": str(chitti.id),
                "chitti_code": chitti.chitti_code,
                "member_id": str(member.id),
                "member_number": member.member_number,
                "cash_received": _money(cash_received),
                "allocated": _money(allocated),
                "available_credit": _money(credit),
                "unresolved_excess": _money(unresolved),
                "outstanding": _money(outstanding),
                "refunded": _money(refunded),
            })
            totals["available_credit"] += credit
            totals["unresolved_excess"] += unresolved
            totals["outstanding"] += outstanding
            totals["cash_received"] += cash_received
            totals["allocated"] += allocated
            totals["refunded"] += refunded
        return {
            "customer_id": str(customer_id),
            "memberships": entries,
            **{key: _money(value) for key, value in totals.items()},
        }

    # ------------------------------------------------------------------
    # Credit application
    # ------------------------------------------------------------------

    async def apply_credit(
        self,
        chitti_id: UUID,
        *,
        member_id,
        source_receipt_id,
        source_period_number: Optional[int],
        target_period_number: int,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
        created_by: Optional[UUID],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        chitti = await self._lock_chitti(chitti_id)
        member = await self._lock_member(chitti, member_id)
        receipt = await self._lock_receipt(chitti, source_receipt_id)
        if receipt.member_id != member.id:
            raise BadRequestException(
                "The receipt does not belong to the selected member.",
                error_code="SOURCE_MEMBER_MISMATCH",
            )
        target = await self.contribution_repo.get_by_chitti_member_period_for_update(
            chitti.id, member.id, target_period_number
        )
        if not target:
            raise BadRequestException(
                "The target contribution period does not exist.",
                error_code="SOURCE_NOT_FOUND",
            )
        amount = self._decimal(amount)
        if amount <= 0:
            raise BadRequestException("Credit amount must be greater than zero.")


        fingerprint = self._fingerprint(
            operation="CREDIT_APPLICATION",
            chitti_id=chitti.id,
            member_id=member.id,
            source_receipt_id=receipt.id,
            source_period_number=source_period_number,
            target_period_number=target_period_number,
            amount=amount,
        )
        replay = await self._replay(
            idempotency_key, fingerprint, "CHITTI_CREDIT_UTILIZED"
        )
        if replay:
            return replay
        contributions = await self.contribution_repo.get_by_member_id(member.id)
        effective = await self.base._effective_contribution_values(chitti, contributions)
        allocations = await self.allocation_repo.get_by_member_id(chitti.id, member.id)
        legs = [
            row for row in allocations if row.source_transaction_id == receipt.id
        ]
        if source_period_number is None:
            available = sum(
                (self._decimal(row.amount) for row in legs
                 if row.allocation_type == "CREDIT"),
                Decimal("0"),
            )
        else:
            source = next(
                (row for row in contributions
                 if row.period_number == source_period_number),
                None,
            )
            if not source:
                raise BadRequestException(
                    "The source contribution period does not exist.",
                    error_code="SOURCE_NOT_FOUND",
                )
            headroom = max(
                self._decimal(source.paid_amount)
                - self._decimal(effective[source.id]["expected"]),
                Decimal("0"),
            )
            source_legs = sum(
                (self._decimal(row.amount) for row in legs
                 if row.allocation_type == "CONTRIBUTION"
                 and row.contribution_id == source.id),
                Decimal("0"),
            )
            available = min(headroom, source_legs)
        if available <= 0:
            raise BadRequestException(
                "The selected receipt has no resolvable balance in that bucket.",
                error_code="NO_ELIGIBLE_BALANCE",
            )
        if amount > available:
            raise BadRequestException(
                "The amount exceeds the credit available on that receipt.",
                error_code="AMOUNT_EXCEEDS_CREDIT",
            )
        remaining = self._decimal(effective[target.id]["remaining"])
        if amount > remaining:
            raise BadRequestException(
                "The amount exceeds the outstanding balance of the target period.",
                error_code="TARGET_PERIOD_OVERPAID",
            )


        transaction = await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="CREDIT_UTILIZATION",
            member_id=member.id,
            amount=amount,
            payment_method=None,
            reference_number=None,
            period_number=target_period_number,
            notes=reason,
            payment_date=today_ist(),
            idempotency_key=idempotency_key,
            created_by=created_by,
        )
        await self.allocation_repo.create(
            chitti_id=chitti.id,
            member_id=member.id,
            source_transaction_id=receipt.id,
            event_transaction_id=transaction.id,
            contribution_id=None,
            allocation_type="CREDIT",
            event_type="CREDIT_UTILIZATION",
            amount=-amount,
        )
        await self.allocation_repo.create(
            chitti_id=chitti.id,
            member_id=member.id,
            source_transaction_id=receipt.id,
            event_transaction_id=transaction.id,
            contribution_id=target.id,
            allocation_type="CONTRIBUTION",
            event_type="CREDIT_UTILIZATION",
            amount=amount,
        )
        await self._save_contribution(
            chitti,
            target,
            self._decimal(target.paid_amount) + amount,
            self._decimal(effective[target.id]["expected"]),
        )
        await self.base._sync_period_schedules_from_contributions(chitti)
        await self.base._refresh_member_financials(chitti, member)

        response = {
            "transaction_id": str(transaction.id),
            "member_id": str(member.id),
            "source_receipt_id": str(receipt.id),
            "target_period_number": target_period_number,
            "amount": _money(amount),
            "allocated_amount": _money(amount),
            "duplicate": False,
        }
        audit = await self._audit(
            action="CHITTI_CREDIT_UTILIZED",
            entity_id=transaction.id,
            user_id=created_by,
            fingerprint=fingerprint,
            response={**response, "duplicate": False},
            extra={
                "chitti_id": str(chitti.id),
                "member_id": str(member.id),
                "source_receipt_id": str(receipt.id),
                "target_period_number": target_period_number,
                "amount": str(amount),
                "reason": reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {**response, "audit_log_id": str(audit.id)}

    async def reverse_credit_utilization(
        self,
        chitti_id: UUID,
        utilization_id: UUID,
        *,
        reason: str,
        reversed_by: Optional[UUID],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        chitti = await self._lock_chitti(chitti_id)
        original = await self.txn_repo.get_by_id_for_update(utilization_id)
        if (
            not original
            or original.chitti_id != chitti.id
            or original.transaction_type != "CREDIT_UTILIZATION"
            or original.original_transaction_id is not None
        ):
            raise NotFoundException("Credit application", utilization_id)
        if not original.member_id:
            raise BadRequestException("The credit application has no member.")
        member = await self._lock_member(chitti, original.member_id)

        key = f"credit-utilization-reversal-{original.id}"
        fingerprint = self._fingerprint(
            operation="CREDIT_UTILIZATION_REVERSAL",
            utilization_id=original.id,
            reason=reason,
        )
        replay = await self._replay(
            key, fingerprint, "CHITTI_CREDIT_UTILIZATION_REVERSED"
        )
        if replay:
            return replay

        legs = await self.allocation_repo.get_by_event_transaction_id(original.id)
        reversal = await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="CREDIT_UTILIZATION",
            member_id=member.id,
            amount=original.amount,
            payment_method=None,
            reference_number=None,
            period_number=original.period_number,
            notes=f"Reversal of {original.id}: {reason}",
            payment_date=today_ist(),
            idempotency_key=key,
            created_by=reversed_by,
            original_transaction_id=original.id,
        )
        contributions = {
            row.id: row for row in await self.contribution_repo.get_by_member_id(member.id)
        }
        effective = await self.base._effective_contribution_values(
            chitti, list(contributions.values())
        )
        for leg in legs:
            await self.allocation_repo.create(
                chitti_id=chitti.id,
                member_id=member.id,
                source_transaction_id=leg.source_transaction_id,
                event_transaction_id=reversal.id,
                contribution_id=leg.contribution_id,
                allocation_type=leg.allocation_type,
                event_type="CREDIT_UTILIZATION",
                amount=-self._decimal(leg.amount),
            )
            if leg.allocation_type == "CONTRIBUTION" and leg.contribution_id:
                contribution = contributions.get(leg.contribution_id)
                if not contribution:
                    raise BadRequestException(
                        "The credit application references a missing contribution.",
                        error_code="PAYMENT_ALLOCATION_MISMATCH",
                    )
                await self._save_contribution(
                    chitti,
                    contribution,
                    self._decimal(contribution.paid_amount) - self._decimal(leg.amount),
                    self._decimal(effective[contribution.id]["expected"]),
                )
        await self.base._sync_period_schedules_from_contributions(chitti)
        await self.base._refresh_member_financials(chitti, member)

        response = {
            "transaction_id": str(reversal.id),
            "original_transaction_id": str(original.id),
            "member_id": str(member.id),
            "amount": _money(original.amount),
            "duplicate": False,
        }
        audit = await self._audit(
            action="CHITTI_CREDIT_UTILIZATION_REVERSED",
            entity_id=reversal.id,
            user_id=reversed_by,
            fingerprint=fingerprint,
            response={**response, "duplicate": False},
            extra={
                "chitti_id": str(chitti.id),
                "reason": reason,
                "reversal_id": str(reversal.id),
            },
            previous={
                "transaction_id": str(original.id),
                "amount": str(original.amount),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {**response, "audit_log_id": str(audit.id)}

    # ------------------------------------------------------------------
    # Unresolved excess -> credit
    # ------------------------------------------------------------------

    async def resolve_excess(
        self,
        chitti_id: UUID,
        *,
        member_id,
        source_receipt_id,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
        created_by: Optional[UUID],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        chitti = await self._lock_chitti(chitti_id)
        member = await self._lock_member(chitti, member_id)
        receipt = await self._lock_receipt(chitti, source_receipt_id)
        if receipt.member_id != member.id:
            raise BadRequestException(
                "The receipt does not belong to the selected member.",
                error_code="SOURCE_MEMBER_MISMATCH",
            )
        amount = self._decimal(amount)
        if amount <= 0:
            raise BadRequestException("Resolution amount must be greater than zero.")


        fingerprint = self._fingerprint(
            operation="EXCESS_RESOLUTION",
            chitti_id=chitti.id,
            member_id=member.id,
            source_receipt_id=receipt.id,
            amount=amount,
        )
        replay = await self._replay(
            idempotency_key, fingerprint, "CHITTI_EXCESS_RESOLVED"
        )
        if replay:
            return replay

        allocations = await self.allocation_repo.get_by_member_id(chitti.id, member.id)
        unresolved = self._unresolved_balances(allocations).get(receipt.id, Decimal("0"))
        if unresolved <= 0:
            raise BadRequestException(
                "This receipt has no unresolved excess.",
                error_code="NO_ELIGIBLE_BALANCE",
            )
        if amount > unresolved:
            raise BadRequestException(
                "The amount exceeds the unresolved excess on that receipt.",
                error_code="AMOUNT_EXCEEDS_UNRESOLVED",
            )


        transaction = await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="EXCESS_RESOLUTION",
            member_id=member.id,
            amount=amount,
            payment_method=None,
            reference_number=None,
            period_number=receipt.period_number,
            notes=reason,
            payment_date=today_ist(),
            idempotency_key=idempotency_key,
            created_by=created_by,
        )
        await self.allocation_repo.create(
            chitti_id=chitti.id,
            member_id=member.id,
            source_transaction_id=receipt.id,
            event_transaction_id=transaction.id,
            contribution_id=None,
            allocation_type="UNRESOLVED",
            event_type="EXCESS_RESOLUTION",
            amount=-amount,
        )
        await self.allocation_repo.create(
            chitti_id=chitti.id,
            member_id=member.id,
            source_transaction_id=receipt.id,
            event_transaction_id=transaction.id,
            contribution_id=None,
            allocation_type="CREDIT",
            event_type="EXCESS_RESOLUTION",
            amount=amount,
        )
        await self.base._refresh_member_financials(chitti, member)

        response = {
            "transaction_id": str(transaction.id),
            "member_id": str(member.id),
            "source_receipt_id": str(receipt.id),
            "amount": _money(amount),
            "available_credit": _money(
                self._credit_balances(
                    await self.allocation_repo.get_by_member_id(chitti.id, member.id)
                ).get(receipt.id, Decimal("0"))
            ),
            "unresolved_excess": _money(
                self._unresolved_balances(
                    await self.allocation_repo.get_by_member_id(chitti.id, member.id)
                ).get(receipt.id, Decimal("0"))
            ),
            "duplicate": False,
        }
        audit = await self._audit(
            action="CHITTI_EXCESS_RESOLVED",
            entity_id=transaction.id,
            user_id=created_by,
            fingerprint=fingerprint,
            response={**response, "duplicate": False},
            extra={
                "chitti_id": str(chitti.id),
                "member_id": str(member.id),
                "source_receipt_id": str(receipt.id),
                "amount": str(amount),
                "reason": reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {**response, "audit_log_id": str(audit.id)}

    async def reverse_excess_resolution(
        self,
        chitti_id: UUID,
        resolution_id: UUID,
        *,
        reason: str,
        reversed_by: Optional[UUID],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        chitti = await self._lock_chitti(chitti_id)
        original = await self.txn_repo.get_by_id_for_update(resolution_id)
        if (
            not original
            or original.chitti_id != chitti.id
            or original.transaction_type != "EXCESS_RESOLUTION"
            or original.original_transaction_id is not None
        ):
            raise NotFoundException("Excess resolution", resolution_id)
        if not original.member_id:
            raise BadRequestException("The excess resolution has no member.")
        member = await self._lock_member(chitti, original.member_id)

        key = f"excess-resolution-reversal-{original.id}"
        fingerprint = self._fingerprint(
            operation="EXCESS_RESOLUTION_REVERSAL",
            resolution_id=original.id,
            reason=reason,
        )
        replay = await self._replay(
            key, fingerprint, "CHITTI_EXCESS_RESOLUTION_REVERSED"
        )
        if replay:
            return replay

        legs = await self.allocation_repo.get_by_event_transaction_id(original.id)
        for leg in legs:
            if leg.allocation_type != "CREDIT":
                continue
            available = self._credit_balances(
                await self.allocation_repo.get_by_member_id(chitti.id, member.id)
            ).get(leg.source_transaction_id, Decimal("0"))
            if available < self._decimal(leg.amount):
                raise BadRequestException(
                    "The resolved credit has already been used; reverse that "
                    "application first.",
                    error_code="NO_ELIGIBLE_BALANCE",
                )
        reversal = await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="EXCESS_RESOLUTION",
            member_id=member.id,
            amount=original.amount,
            payment_method=None,
            reference_number=None,
            period_number=original.period_number,
            notes=f"Reversal of {original.id}: {reason}",
            payment_date=today_ist(),
            idempotency_key=key,
            created_by=reversed_by,
            original_transaction_id=original.id,
        )
        for leg in legs:
            await self.allocation_repo.create(
                chitti_id=chitti.id,
                member_id=member.id,
                source_transaction_id=leg.source_transaction_id,
                event_transaction_id=reversal.id,
                contribution_id=None,
                allocation_type=leg.allocation_type,
                event_type="EXCESS_RESOLUTION",
                amount=-self._decimal(leg.amount),
            )
        await self.base._refresh_member_financials(chitti, member)

        response = {
            "transaction_id": str(reversal.id),
            "original_transaction_id": str(original.id),
            "member_id": str(member.id),
            "amount": _money(original.amount),
            "duplicate": False,
        }
        audit = await self._audit(
            action="CHITTI_EXCESS_RESOLUTION_REVERSED",
            entity_id=reversal.id,
            user_id=reversed_by,
            fingerprint=fingerprint,
            response={**response, "duplicate": False},
            extra={
                "chitti_id": str(chitti.id),
                "reason": reason,
                "reversal_id": str(reversal.id),
            },
            previous={
                "transaction_id": str(original.id),
                "amount": str(original.amount),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {**response, "audit_log_id": str(audit.id)}

    # ------------------------------------------------------------------
    # Over-allocation (paid above the instalment) resolution
    # ------------------------------------------------------------------

    async def _overallocation_rows(self, chitti, member):
        contributions = await self.contribution_repo.get_by_member_id(member.id)
        effective = await self.base._effective_contribution_values(chitti, contributions)
        allocations = await self.allocation_repo.get_by_member_id(chitti.id, member.id)
        funding: dict[UUID, dict[UUID, Decimal]] = {}
        for allocation in allocations:
            if allocation.allocation_type != "CONTRIBUTION" or not allocation.contribution_id:
                continue
            entry = funding.setdefault(allocation.contribution_id, {})
            entry[allocation.source_transaction_id] = (
                entry.get(allocation.source_transaction_id, Decimal("0"))
                + self._decimal(allocation.amount)
            )
        rows = []
        for contribution in sorted(contributions, key=lambda row: row.period_number):
            paid = self._decimal(contribution.paid_amount)
            expected = self._decimal(effective[contribution.id]["expected"])
            excess = max(paid - expected, Decimal("0"))
            if excess <= 0:
                continue
            rows.append({
                "contribution_id": contribution.id,
                "period_number": contribution.period_number,
                "paid_amount": paid,
                "expected_amount": expected,
                "overallocated_amount": excess,
                "funding": [
                    {"receipt_id": source_id, "amount": amount}
                    for source_id, amount in funding.get(contribution.id, {}).items()
                    if amount > 0
                ],
            })
        return rows, effective, contributions, funding

    async def list_overallocations(self, chitti_id: UUID, member_id: UUID) -> dict:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        member = await self.member_repo.get_by_id(member_id)
        if not member or member.chitti_id != chitti.id:
            raise NotFoundException("Member", member_id)
        rows, _, _, _ = await self._overallocation_rows(chitti, member)
        return {
            "chitti_id": str(chitti.id),
            "member_id": str(member.id),
            "overallocations": [
                {
                    **row,
                    "contribution_id": str(row["contribution_id"]),
                    "paid_amount": _money(row["paid_amount"]),
                    "expected_amount": _money(row["expected_amount"]),
                    "overallocated_amount": _money(row["overallocated_amount"]),
                    "funding": [
                        {
                            "receipt_id": str(item["receipt_id"]),
                            "amount": _money(item["amount"]),
                        }
                        for item in row["funding"]
                    ],
                }
                for row in rows
            ],
            "total_overallocated": _money(
                sum((row["overallocated_amount"] for row in rows), Decimal("0"))
            ),
        }

    async def resolve_overallocation(
        self,
        chitti_id: UUID,
        *,
        member_id,
        source_period_number: int,
        source_receipt_id,
        mode: str,
        amount: Decimal,
        target_period_number: Optional[int],
        reason: str,
        idempotency_key: str,
        created_by: Optional[UUID],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        if mode not in ("REALLOCATE", "TO_CREDIT"):
            raise BadRequestException("Resolution mode must be REALLOCATE or TO_CREDIT.")
        chitti = await self._lock_chitti(chitti_id)
        member = await self._lock_member(chitti, member_id)
        receipt = await self._lock_receipt(chitti, source_receipt_id)
        if receipt.member_id != member.id:
            raise BadRequestException(
                "The receipt does not belong to the selected member.",
                error_code="SOURCE_MEMBER_MISMATCH",
            )
        amount = self._decimal(amount)
        if amount <= 0:
            raise BadRequestException("Resolution amount must be greater than zero.")


        fingerprint = self._fingerprint(
            operation="OVERALLOCATION_RESOLUTION",
            chitti_id=chitti.id,
            member_id=member.id,
            source_period_number=source_period_number,
            source_receipt_id=receipt.id,
            mode=mode,
            amount=amount,
            target_period_number=target_period_number,
        )
        action = (
            "CHITTI_OVERALLOCATION_REALLOCATED"
            if mode == "REALLOCATE"
            else "CHITTI_OVERALLOCATION_TO_CREDIT"
        )
        replay = await self._replay(idempotency_key, fingerprint, action)
        if replay:
            return replay
        rows, effective, contributions, funding = await self._overallocation_rows(
            chitti, member
        )
        source_row = next(
            (row for row in rows if row["period_number"] == source_period_number), None
        )
        if not source_row:
            raise BadRequestException(
                "That period is not over-allocated.",
                error_code="NOT_OVERALLOCATED",
            )
        if amount > source_row["overallocated_amount"]:
            raise BadRequestException(
                "The amount exceeds the over-allocated balance.",
                error_code="AMOUNT_EXCEEDS_REFUNDABLE",
            )
        available = funding.get(source_row["contribution_id"], {}).get(receipt.id, Decimal("0"))
        if amount > available:
            raise BadRequestException(
                "The selected receipt did not fund that much of the period.",
                error_code="AMOUNT_EXCEEDS_SOURCE",
            )
        target = None
        if mode == "REALLOCATE":
            if target_period_number is None:
                raise BadRequestException(
                    "A target period is required for reallocation.",
                    error_code="TARGET_PERIOD_REQUIRED",
                )
            target = next(
                (row for row in contributions if row.period_number == target_period_number),
                None,
            )
            if not target:
                raise BadRequestException(
                    "The target contribution period does not exist.",
                    error_code="SOURCE_NOT_FOUND",
                )
            if self._decimal(effective[target.id]["remaining"]) < amount:
                raise BadRequestException(
                    "The target period does not have that much outstanding.",
                    error_code="TARGET_PERIOD_OVERPAID",
                )


        transaction = await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="EXCESS_RESOLUTION",
            member_id=member.id,
            amount=amount,
            payment_method=None,
            reference_number=None,
            period_number=source_period_number,
            notes=reason,
            payment_date=today_ist(),
            idempotency_key=idempotency_key,
            created_by=created_by,
        )
        await self.allocation_repo.create(
            chitti_id=chitti.id,
            member_id=member.id,
            source_transaction_id=receipt.id,
            event_transaction_id=transaction.id,
            contribution_id=source_row["contribution_id"],
            allocation_type="CONTRIBUTION",
            event_type="EXCESS_RESOLUTION",
            amount=-amount,
        )
        if mode == "REALLOCATE":
            await self.allocation_repo.create(
                chitti_id=chitti.id,
                member_id=member.id,
                source_transaction_id=receipt.id,
                event_transaction_id=transaction.id,
                contribution_id=target.id,
                allocation_type="CONTRIBUTION",
                event_type="EXCESS_RESOLUTION",
                amount=amount,
            )
            await self._save_contribution(
                chitti, target,
                self._decimal(target.paid_amount) + amount,
                self._decimal(effective[target.id]["expected"]),
            )
        else:
            await self.allocation_repo.create(
                chitti_id=chitti.id,
                member_id=member.id,
                source_transaction_id=receipt.id,
                event_transaction_id=transaction.id,
                contribution_id=None,
                allocation_type="CREDIT",
                event_type="EXCESS_RESOLUTION",
                amount=amount,
            )
        source_contribution = next(
            (row for row in contributions if row.id == source_row["contribution_id"])
        )
        await self._save_contribution(
            chitti,
            source_contribution,
            self._decimal(source_contribution.paid_amount) - amount,
            self._decimal(effective[source_contribution.id]["expected"]),
        )
        await self.base._sync_period_schedules_from_contributions(chitti)
        await self.base._refresh_member_financials(chitti, member)

        response = {
            "transaction_id": str(transaction.id),
            "member_id": str(member.id),
            "mode": mode,
            "source_period_number": source_period_number,
            "source_receipt_id": str(receipt.id),
            "target_period_number": target_period_number,
            "amount": _money(amount),
            "duplicate": False,
        }
        audit = await self._audit(
            action=action,
            entity_id=transaction.id,
            user_id=created_by,
            fingerprint=fingerprint,
            response={**response, "duplicate": False},
            extra={
                "chitti_id": str(chitti.id),
                "member_id": str(member.id),
                "source_period_number": source_period_number,
                "source_receipt_id": str(receipt.id),
                "mode": mode,
                "amount": str(amount),
                "reason": reason,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {**response, "audit_log_id": str(audit.id)}

    async def reverse_overallocation_resolution(
        self,
        chitti_id: UUID,
        resolution_id: UUID,
        *,
        reason: str,
        reversed_by: Optional[UUID],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        chitti = await self._lock_chitti(chitti_id)
        original = await self.txn_repo.get_by_id_for_update(resolution_id)
        if (
            not original
            or original.chitti_id != chitti.id
            or original.transaction_type != "EXCESS_RESOLUTION"
            or original.original_transaction_id is not None
        ):
            raise NotFoundException("Over-allocation resolution", resolution_id)
        if not original.member_id:
            raise BadRequestException("The resolution has no member.")
        member = await self._lock_member(chitti, original.member_id)
        legs = await self.allocation_repo.get_by_event_transaction_id(original.id)
        if not legs:
            raise ConflictException(
                "The resolution has no recorded allocation legs.",
                error_code="PAYMENT_ALLOCATION_MISMATCH",
            )

        key = f"overallocation-reversal-{original.id}"
        fingerprint = self._fingerprint(
            operation="OVERALLOCATION_REVERSAL",
            resolution_id=original.id,
            reason=reason,
        )
        replay = await self._replay(
            key, fingerprint, "CHITTI_OVERALLOCATION_RESOLUTION_REVERSED"
        )
        if replay:
            return replay

        for leg in legs:
            if leg.allocation_type == "CREDIT" and self._decimal(leg.amount) > 0:
                available = self._credit_balances(
                    await self.allocation_repo.get_by_member_id(chitti.id, member.id)
                ).get(leg.source_transaction_id, Decimal("0"))
                if available < self._decimal(leg.amount):
                    raise BadRequestException(
                        "The resolved credit has already been used; reverse that "
                        "application first.",
                        error_code="NO_ELIGIBLE_BALANCE",
                    )

        contributions = {
            row.id: row for row in await self.contribution_repo.get_by_member_id(member.id)
        }
        effective = await self.base._effective_contribution_values(
            chitti, list(contributions.values())
        )
        reversal = await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="EXCESS_RESOLUTION",
            member_id=member.id,
            amount=original.amount,
            payment_method=None,
            reference_number=None,
            period_number=original.period_number,
            notes=f"Reversal of {original.id}: {reason}",
            payment_date=today_ist(),
            idempotency_key=key,
            created_by=reversed_by,
            original_transaction_id=original.id,
        )
        for leg in legs:
            await self.allocation_repo.create(
                chitti_id=chitti.id,
                member_id=member.id,
                source_transaction_id=leg.source_transaction_id,
                event_transaction_id=reversal.id,
                contribution_id=leg.contribution_id,
                allocation_type=leg.allocation_type,
                event_type="EXCESS_RESOLUTION",
                amount=-self._decimal(leg.amount),
            )
            if leg.allocation_type == "CONTRIBUTION" and leg.contribution_id:
                contribution = contributions.get(leg.contribution_id)
                if not contribution:
                    raise BadRequestException(
                        "The resolution references a missing contribution.",
                        error_code="PAYMENT_ALLOCATION_MISMATCH",
                    )
                await self._save_contribution(
                    chitti,
                    contribution,
                    self._decimal(contribution.paid_amount) - self._decimal(leg.amount),
                    self._decimal(effective[contribution.id]["expected"]),
                )
        await self.base._sync_period_schedules_from_contributions(chitti)
        await self.base._refresh_member_financials(chitti, member)

        response = {
            "transaction_id": str(reversal.id),
            "original_transaction_id": str(original.id),
            "member_id": str(member.id),
            "amount": _money(original.amount),
            "duplicate": False,
        }
        audit = await self._audit(
            action="CHITTI_OVERALLOCATION_RESOLUTION_REVERSED",
            entity_id=reversal.id,
            user_id=reversed_by,
            fingerprint=fingerprint,
            response={**response, "duplicate": False},
            extra={
                "chitti_id": str(chitti.id),
                "reason": reason,
                "reversal_id": str(reversal.id),
            },
            previous={
                "transaction_id": str(original.id),
                "amount": str(original.amount),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {**response, "audit_log_id": str(audit.id)}

    # ------------------------------------------------------------------
    # Refunds (cash out)
    # ------------------------------------------------------------------

    async def refund(
        self,
        chitti_id: UUID,
        *,
        source_receipt_id,
        source_bucket: str,
        source_member_id,
        source_period_number: Optional[int],
        amount: Decimal,
        refund_method: str,
        reference_number: Optional[str],
        reason: str,
        idempotency_key: str,
        created_by: Optional[UUID],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        if source_bucket not in ("CONTRIBUTION", "CREDIT"):
            raise BadRequestException(
                "Refund source must be CONTRIBUTION or CREDIT.",
                error_code="SOURCE_NOT_FOUND",
            )
        if source_bucket == "CONTRIBUTION" and source_period_number is None:
            raise BadRequestException(
                "A contribution refund requires the source period.",
                error_code="SOURCE_PERIOD_REQUIRED",
            )
        if source_bucket == "CREDIT" and source_period_number is not None:
            raise BadRequestException(
                "A credit refund must not name a contribution period.",
                error_code="SOURCE_PERIOD_NOT_ALLOWED",
            )
        if not refund_method:
            raise BadRequestException(
                "A refund method is required.",
                error_code="REFUND_METHOD_REQUIRED",
            )
        chitti = await self._lock_chitti(chitti_id)
        member = await self._lock_member(chitti, source_member_id)
        receipt = await self._lock_receipt(chitti, source_receipt_id)
        if receipt.member_id != member.id:
            raise BadRequestException(
                "The receipt does not belong to the selected member.",
                error_code="SOURCE_MEMBER_MISMATCH",
            )
        already_reversed = await self.txn_repo.get_by_idempotency_key(
            f"reversal-{receipt.id}"
        )
        if already_reversed:
            raise BadRequestException(
                "This receipt has already been reversed.",
                error_code="REVERSED_RECEIPT",
            )
        amount = self._decimal(amount)
        if amount <= 0:
            raise BadRequestException("Refund amount must be greater than zero.")


        fingerprint = self._fingerprint(
            operation="REFUND",
            chitti_id=chitti.id,
            source_receipt_id=receipt.id,
            source_bucket=source_bucket,
            source_member_id=member.id,
            source_period_number=source_period_number,
            amount=amount,
            refund_method=refund_method,
            reference_number=reference_number,
        )
        replay = await self._replay(
            idempotency_key, fingerprint, "CHITTI_OVERALLOCATION_REFUNDED"
        )
        if replay:
            return replay
        contributions = await self.contribution_repo.get_by_member_id(member.id)
        effective = await self.base._effective_contribution_values(chitti, contributions)
        allocations = await self.allocation_repo.get_by_source_transaction_id(receipt.id)
        contribution = None
        if source_bucket == "CONTRIBUTION":
            contribution = await self.contribution_repo.get_by_chitti_member_period_for_update(
                chitti.id, member.id, source_period_number
            )
            if not contribution:
                raise BadRequestException(
                    "The source contribution period does not exist.",
                    error_code="SOURCE_NOT_FOUND",
                )
            headroom = max(
                self._decimal(contribution.paid_amount)
                - self._decimal(effective[contribution.id]["expected"]),
                Decimal("0"),
            )
            legs = sum(
                (self._decimal(row.amount) for row in allocations
                 if row.allocation_type == "CONTRIBUTION"
                 and row.contribution_id == contribution.id),
                Decimal("0"),
            )
            eligible = min(headroom, legs)
        else:
            eligible = sum(
                (self._decimal(row.amount) for row in allocations
                 if row.allocation_type == "CREDIT"),
                Decimal("0"),
            )
        if eligible <= 0:
            raise BadRequestException(
                "The selected bucket has nothing refundable.",
                error_code="NO_ELIGIBLE_BALANCE",
            )
        if amount > eligible:
            raise BadRequestException(
                "The amount exceeds what is refundable from that bucket.",
                error_code="AMOUNT_EXCEEDS_REFUNDABLE",
            )


        transaction = await self.txn_repo.create(
            chitti_id=chitti.id,
            transaction_type="REFUND",
            member_id=member.id,
            amount=amount,
            payment_method=refund_method,
            reference_number=reference_number,
            period_number=source_period_number,
            notes=reason,
            payment_date=today_ist(),
            idempotency_key=idempotency_key,
            created_by=created_by,
        )
        await self.allocation_repo.create(
            chitti_id=chitti.id,
            member_id=member.id,
            source_transaction_id=receipt.id,
            event_transaction_id=transaction.id,
            contribution_id=contribution.id if contribution else None,
            allocation_type=source_bucket,
            event_type="EXCESS_RESOLUTION",
            amount=-amount,
        )
        if contribution is not None:
            await self._save_contribution(
                chitti,
                contribution,
                self._decimal(contribution.paid_amount) - amount,
                self._decimal(effective[contribution.id]["expected"]),
            )
        await self.base._sync_period_schedules_from_contributions(chitti)
        await self.base._refresh_member_financials(chitti, member)

        refunded = await self.base._refunded_amount(receipt.id)
        remaining = max(self._decimal(receipt.amount) - refunded, Decimal("0"))
        response = {
            "transaction_id": str(transaction.id),
            "source_receipt_id": str(receipt.id),
            "source_bucket": source_bucket,
            "member_id": str(member.id),
            "period_number": source_period_number,
            "amount": _money(amount),
            "refund_method": refund_method,
            "cumulative_refunded": _money(refunded),
            "remaining_refundable": _money(remaining),
            "duplicate": False,
        }
        audit = await self._audit(
            action="CHITTI_OVERALLOCATION_REFUNDED",
            entity_id=transaction.id,
            user_id=created_by,
            fingerprint=fingerprint,
            response={**response, "duplicate": False},
            extra={
                "chitti_id": str(chitti.id),
                "source_receipt_id": str(receipt.id),
                "source_bucket": source_bucket,
                "source_period_number": source_period_number,
                "amount": str(amount),
                "refund_method": refund_method,
                "reason": reason,
                "irreversible": True,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {**response, "audit_log_id": str(audit.id)}

    async def list_refunds(
        self, chitti_id: UUID, receipt_id: Optional[UUID] = None
    ) -> list[dict]:
        chitti = await self.chitti_repo.get_by_id(chitti_id)
        if not chitti:
            raise NotFoundException("Chitti", chitti_id)
        refunds = await self.txn_repo.get_by_chitti_and_type(chitti.id, "REFUND")
        result = []
        for refund in refunds:
            legs = await self.allocation_repo.get_by_event_transaction_id(refund.id)
            sources = {leg.source_transaction_id for leg in legs}
            if receipt_id and sources != {receipt_id}:
                continue
            result.append({
                "transaction_id": str(refund.id),
                "source_receipt_ids": [str(source) for source in sources],
                "member_id": str(refund.member_id) if refund.member_id else None,
                "amount": _money(refund.amount),
                "refund_method": refund.payment_method,
                "reference_number": refund.reference_number,
                "period_number": refund.period_number,
                "notes": refund.notes,
                "created_at": str(refund.created_at),
            })
        return result
