"""
Customer management service — full onboarding fields.
"""

import re
from typing import Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.repositories.customer_repo import CustomerRepository
from app.services.audit_service import AuditService
from app.utils.codes import generate_customer_code
from app.utils.validators import validate_mobile_number


# Customer-facing status for every Chitti ledger event. Only contributions are
# "successful payments"; credits, refunds and payouts remain visible without
# inflating the customer's paid total.
CHITTI_LEDGER_STATUS = {
    "CONTRIBUTION": "COMPLETED",
    "REVERSAL": "REVERSED",
    "REFUND": "REFUNDED",
    "CREDIT_UTILIZATION": "CREDIT_APPLIED",
    "EXCESS_RESOLUTION": "CREDIT_ADDED",
    "LIFT_ADJUSTMENT": "ADJUSTED",
    "PAYOUT": "PAID_OUT",
    "PENALTY": "CHARGED",
    "FEE": "CHARGED",
}


def _audit_value(value: object) -> object:
    """Make a scalar safe for JSONB audit columns."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _normalize_mobile(value: object) -> str:
    """Store one canonical form so formatted variants cannot bypass uniqueness."""
    cleaned = re.sub(r"[\s\-+]", "", str(value))
    if cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    return cleaned


CLEARABLE_CUSTOMER_FIELDS = {
    "alternate_mobile",
    "email",
    "date_of_birth",
    "gender",
    "address",
    "city",
    "state",
    "pincode",
    "pan_number",
    "aadhar_number",
    "occupation",
    "nominee_name",
    "nominee_phone",
    "nominee_relation",
    "notes",
}


class CustomerService:
    """Customer CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.customer_repo = CustomerRepository(session)

    async def create_customer(
        self,
        *,
        actor_id: Optional[UUID] = None,
        **kwargs,
    ) -> dict:
        """Create a new customer with auto-generated code."""
        mobile_number = kwargs.get("mobile_number")
        if not mobile_number:
            raise ConflictException("Mobile number is required.")
        mobile_number = _normalize_mobile(mobile_number)
        if not validate_mobile_number(mobile_number):
            raise ConflictException("Enter a valid 10-digit Indian mobile number.")
        kwargs["mobile_number"] = mobile_number

        existing = await self.customer_repo.get_by_mobile(mobile_number)
        if existing:
            raise ConflictException(
                f"Customer with mobile number {mobile_number} already exists.",
                error_code="DUPLICATE_CUSTOMER_MOBILE",
            )

        values = {k: v for k, v in kwargs.items() if v is not None}
        # A savepoint makes the unique indexes the final guard against
        # concurrent registrations; a code collision is retried with a fresh
        # sequence value instead of becoming an opaque 500.
        for _attempt in range(3):
            customer_code = await generate_customer_code(self.session)
            try:
                customer = await self.customer_repo.create_with_savepoint(
                    customer_code=customer_code,
                    status="ACTIVE",
                    **values,
                )
                payload = self._to_dict(customer)
                await AuditService(self.session).log(
                    user_id=actor_id,
                    action="CUSTOMER_CREATED",
                    entity_type="CUSTOMER",
                    entity_id=customer.id,
                    new_value={
                        "customer_code": customer.customer_code,
                        "full_name": customer.full_name,
                        "mobile_number": customer.mobile_number,
                    },
                )
                return payload
            except IntegrityError as exc:
                detail = str(exc.orig).lower()
                if "uq_customer_mobile_digits" in detail:
                    raise ConflictException(
                        f"Customer with mobile number {mobile_number} already exists.",
                        error_code="DUPLICATE_CUSTOMER_MOBILE",
                    ) from exc
                if "customer_code" in detail and _attempt < 2:
                    continue
                raise ConflictException(
                    "Unable to register customer; please retry.",
                    error_code="CUSTOMER_REGISTRATION_CONFLICT",
                ) from exc
        raise ConflictException(
            "Unable to register customer; please retry.",
            error_code="CUSTOMER_REGISTRATION_CONFLICT",
        )

    async def get_customer(self, customer_id: UUID) -> dict:
        customer = await self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundException("Customer", customer_id)
        return self._to_dict(customer)

    async def list_customers(
        self,
        page: int = 1,
        per_page: int = 25,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        if search:
            start = (page - 1) * per_page
            customers, total = await self.customer_repo.search(
                search, skip=start, limit=per_page, status=status
            )
        else:
            filters = {}
            if status:
                filters["status"] = status
            skip = (page - 1) * per_page
            customers, total = await self.customer_repo.get_all(
                skip=skip, limit=per_page, filters=filters
            )
        return [self._to_dict(c) for c in customers], total

    async def update_customer(
        self,
        customer_id: UUID,
        *,
        actor_id: Optional[UUID] = None,
        **kwargs,
    ) -> dict:
        customer = await self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundException("Customer", customer_id)
        updates = {
            k: v
            for k, v in kwargs.items()
            if v is not None or k in CLEARABLE_CUSTOMER_FIELDS
        }
        if "mobile_number" in updates:
            updates["mobile_number"] = _normalize_mobile(updates["mobile_number"])
            if not validate_mobile_number(updates["mobile_number"]):
                raise ConflictException("Enter a valid 10-digit Indian mobile number.")
            duplicate = await self.customer_repo.get_by_mobile_excluding(
                updates["mobile_number"], customer.id
            )
            if duplicate:
                raise ConflictException(
                    "Another customer is already registered with this mobile number.",
                    error_code="DUPLICATE_CUSTOMER_MOBILE",
                )
        if updates:
            previous = {
                key: _audit_value(getattr(customer, key))
                for key in updates
                if hasattr(customer, key)
            }
            try:
                await self.customer_repo.update(
                    customer,
                    allow_none=CLEARABLE_CUSTOMER_FIELDS,
                    **updates,
                )
            except IntegrityError as exc:
                if "uq_customer_mobile_digits" in str(exc.orig).lower():
                    raise ConflictException(
                        "Another customer is already registered with this mobile number.",
                        error_code="DUPLICATE_CUSTOMER_MOBILE",
                    ) from exc
                raise
            await AuditService(self.session).log(
                user_id=actor_id,
                action="CUSTOMER_UPDATED",
                entity_type="CUSTOMER",
                entity_id=customer.id,
                previous_value=previous,
                new_value={
                    key: _audit_value(getattr(customer, key))
                    for key in updates
                    if hasattr(customer, key)
                },
            )
        return self._to_dict(customer)

    async def get_customer_ledger(self, customer_id: UUID) -> dict:
        customer = await self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundException("Customer", customer_id)

        from app.repositories.finance_repo import FinanceAccountRepository
        from app.repositories.chitti_repo import ChittiMemberRepository, ChittiRepository
        from sqlalchemy import select

        from app.models.chitti import (
            Chitti,
            ChittiAgreement,
            ChittiLiftEvent,
            ChittiMember,
            ChittiTransaction,
        )
        from app.models.finance import FinanceAccount, FinanceSchedule
        from app.models.payment import PaymentTransaction

        finance_repo = FinanceAccountRepository(self.session)
        member_repo = ChittiMemberRepository(self.session)
        chitti_repo = ChittiRepository(self.session)

        finance_accounts = await finance_repo.get_by_customer_id(customer_id)
        memberships = await member_repo.get_by_customer_id(customer_id)
        member_ids = [m.id for m in memberships]

        agreements_by_member: dict = {}
        lifts_by_member: dict = {}
        if member_ids:
            agreement_rows = (await self.session.execute(
                select(ChittiAgreement)
                .where(ChittiAgreement.chitti_member_id.in_(member_ids))
                .order_by(ChittiAgreement.created_at.desc())
            )).scalars().all()
            for agreement in agreement_rows:
                # One agreement per slot is normal; keep the newest if history
                # contains a replaced/cancelled document.
                agreements_by_member.setdefault(agreement.chitti_member_id, agreement)

            lift_rows = (await self.session.execute(
                select(ChittiLiftEvent)
                .where(
                    ChittiLiftEvent.member_id.in_(member_ids),
                    ChittiLiftEvent.reversed_at.is_(None),
                )
                .order_by(ChittiLiftEvent.period_number.desc())
            )).scalars().all()
            for lift in lift_rows:
                lifts_by_member.setdefault(lift.member_id, lift)

        chitti_list = []
        for m in memberships:
            chitti = await chitti_repo.get_by_id(m.chitti_id)
            if chitti:
                chitti_list.append({
                    "id": str(chitti.id),
                    "chitti_code": chitti.chitti_code,
                    "name": chitti.name,
                    "status": chitti.status,
                    "member_id": str(m.id),
                    "member_number": m.member_number,
                    "payout_order": m.payout_order,
                    "alias": m.alias,
                    "slot_status": m.status,
                    "total_paid": float(m.total_paid_amount or 0),
                    "outstanding": float(m.outstanding_amount or 0),
                    "agreement_status": (
                        agreements_by_member[m.id].agreement_status
                        if m.id in agreements_by_member else "NOT_GENERATED"
                    ),
                    "agreement_number": (
                        agreements_by_member[m.id].agreement_number
                        if m.id in agreements_by_member else None
                    ),
                    "lift_status": (
                        f"Lifted in period {lifts_by_member[m.id].period_number}"
                        if m.id in lifts_by_member else "Not lifted"
                    ),
                })
        # Read each immutable ledger independently, then combine the rows only
        # for this customer-facing view. Chitti collections are not
        # PaymentTransaction rows: they live in chitti_transactions and are
        # linked to the customer through chitti_members.
        finance_rows = (await self.session.execute(
            select(PaymentTransaction, FinanceAccount.account_number,
                   FinanceSchedule.installment_number)
            .outerjoin(FinanceAccount, FinanceAccount.id == PaymentTransaction.finance_account_id)
            .outerjoin(FinanceSchedule, FinanceSchedule.id == PaymentTransaction.finance_schedule_id)
            .where(PaymentTransaction.customer_id == customer_id)
            .order_by(PaymentTransaction.payment_date.desc(), PaymentTransaction.created_at.desc())
        )).all()
        chitti_rows = (await self.session.execute(
            select(
                ChittiTransaction,
                Chitti.name,
                ChittiMember.member_number,
                ChittiMember.alias,
            )
            .join(ChittiMember, ChittiMember.id == ChittiTransaction.member_id)
            .join(Chitti, Chitti.id == ChittiTransaction.chitti_id)
            .where(ChittiMember.customer_id == customer_id)
            .order_by(ChittiTransaction.payment_date.desc(), ChittiTransaction.created_at.desc())
        )).all()

        finance_history = []
        for payment, account_name, installment_number in finance_rows:
            finance_history.append({
                "id": str(payment.id),
                "transaction_id": payment.transaction_id,
                "source": "FINANCE",
                "customer_name": customer.full_name,
                "account_name": account_name,
                "period_number": installment_number,
                "amount": float(payment.amount),
                "payment_method": payment.payment_method,
                "payment_date": str(payment.payment_date),
                "event_type": None,
                "status": payment.status,
                "is_reversal": payment.is_reversal,
                "reversal_of_transaction_id": None,
                "reversed_by_transaction_id": None,
                "created_at": payment.created_at,
            })
        finance_by_id = {row[0].id: row[0] for row in finance_rows}
        finance_item_by_id = {item["id"]: item for item in finance_history}
        for payment, _, _ in finance_rows:
            if payment.is_reversal and payment.reversed_by in finance_by_id:
                original = finance_by_id[payment.reversed_by]
                finance_item_by_id[str(payment.id)]["reversal_of_transaction_id"] = original.transaction_id
        reversals_by_original = {
            payment.reversed_by: payment.transaction_id
            for payment, _, _ in finance_rows
            if payment.is_reversal and payment.reversed_by
        }
        for payment, _, _ in finance_rows:
            finance_item_by_id[str(payment.id)]["reversed_by_transaction_id"] = reversals_by_original.get(payment.id)

        chitti_history = []
        for transaction, chitti_name, member_number, alias in chitti_rows:
            event_type = transaction.transaction_type
            is_reversal = event_type == "REVERSAL"
            chitti_history.append({
                "id": str(transaction.id),
                "transaction_id": f"CHT-{transaction.id}",
                "source": "CHITTI",
                "customer_name": customer.full_name,
                "account_name": chitti_name,
                "member_id": str(transaction.member_id) if transaction.member_id else None,
                "member_number": member_number,
                "alias": alias,
                "period_number": transaction.period_number,
                "amount": float(transaction.amount),
                "payment_method": transaction.payment_method,
                "payment_date": str(transaction.payment_date) if transaction.payment_date else None,
                "event_type": event_type,
                "status": CHITTI_LEDGER_STATUS.get(event_type, "COMPLETED"),
                "is_reversal": is_reversal,
                "reversal_of_transaction_id": None,
                "reversed_by_transaction_id": None,
                "created_at": transaction.created_at,
                "_notes": transaction.notes,
                "_original_transaction_id": transaction.original_transaction_id,
            })
        chitti_by_id = {str(row[0].id): row[0] for row in chitti_rows}
        chitti_item_by_id = {item["id"]: item for item in chitti_history}
        for item in chitti_history:
            transaction = chitti_by_id[item["id"]]
            if item["is_reversal"]:
                original_id = None
                if transaction.original_transaction_id:
                    original_id = str(transaction.original_transaction_id)
                elif transaction.notes:
                    # Older reversals stored the original UUID only in notes.
                    original_id = transaction.notes.partition(":")[0].removeprefix("Reversal of ")
                original_item = chitti_item_by_id.get(original_id) if original_id else None
                if original_item:
                    item["reversal_of_transaction_id"] = original_item["transaction_id"]
                    if original_item["event_type"] == "CONTRIBUTION":
                        original_item["status"] = "REVERSED"
                        original_item["reversed_by_transaction_id"] = item["transaction_id"]
            item.pop("_notes", None)
            item.pop("_original_transaction_id", None)

        # Deduplicate by ledger and primary key (the two ledgers intentionally
        # remain independent, even if they happen to use the same UUID).
        seen = set()
        payment_history = []
        for item in finance_history + chitti_history:
            key = (item["source"], item["id"])
            if key not in seen:
                seen.add(key)
                payment_history.append(item)
        payment_history.sort(key=lambda item: (item["payment_date"] or "", item["created_at"]), reverse=True)
        for item in payment_history:
            item.pop("created_at", None)
        successful = [item for item in payment_history if item["status"] == "COMPLETED" and not item["is_reversal"]]

        return {
            "customer": self._to_dict(customer),
            "finance_accounts": [
                {
                    "id": str(fa.id),
                    "account_number": fa.account_number,
                    "total_payable": float(fa.total_payable),
                    "status": fa.status,
                }
                for fa in finance_accounts
            ],
            "chittis": chitti_list,
            "payment_history": payment_history,
            "payment_summary": {
                "transaction_count": len(payment_history),
                "successful_transaction_count": len(successful),
                "successful_paid_total": sum(item["amount"] for item in successful),
            },
        }

    def _to_dict(self, c) -> dict:
        return {
            "id": str(c.id),
            "customer_code": c.customer_code,
            "full_name": c.full_name,
            "date_of_birth": str(c.date_of_birth) if c.date_of_birth else None,
            "gender": c.gender,
            "mobile_number": c.mobile_number,
            "alternate_mobile": c.alternate_mobile,
            "email": c.email,
            "address": c.address,
            "city": c.city,
            "state": c.state,
            "pincode": c.pincode,
            "pan_number": c.pan_number,
            "aadhar_number": c.aadhar_number,
            "occupation": c.occupation,
            "nominee_name": c.nominee_name,
            "nominee_phone": c.nominee_phone,
            "nominee_relation": c.nominee_relation,
            "notes": c.notes,
            "status": c.status,
            "created_at": str(c.created_at),
            "updated_at": str(c.updated_at),
        }
