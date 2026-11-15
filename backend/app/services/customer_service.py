"""
Customer management service — full onboarding fields.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.repositories.customer_repo import CustomerRepository
from app.utils.codes import generate_customer_code


class CustomerService:
    """Customer CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.customer_repo = CustomerRepository(session)

    async def create_customer(self, **kwargs) -> dict:
        """Create a new customer with auto-generated code."""
        mobile_number = kwargs.get("mobile_number")
        if not mobile_number:
            raise ConflictException("Mobile number is required.")
        if not any(ch.isdigit() for ch in mobile_number):
            raise ConflictException("Enter a valid mobile number.")

        existing = await self.customer_repo.get_by_mobile(mobile_number)
        if existing:
            raise ConflictException(
                f"Customer with mobile number {mobile_number} already exists."
            )

        customer_code = await generate_customer_code(self.session)
        customer = await self.customer_repo.create(
            customer_code=customer_code,
            status="ACTIVE",
            **{k: v for k, v in kwargs.items() if v is not None},
        )
        return self._to_dict(customer)

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
            customers = await self.customer_repo.search(search)
            total = len(customers)
            start = (page - 1) * per_page
            customers = customers[start : start + per_page]
        else:
            filters = {}
            if status:
                filters["status"] = status
            skip = (page - 1) * per_page
            customers, total = await self.customer_repo.get_all(
                skip=skip, limit=per_page, filters=filters
            )
        return [self._to_dict(c) for c in customers], total

    async def update_customer(self, customer_id: UUID, **kwargs) -> dict:
        customer = await self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundException("Customer", customer_id)
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if "mobile_number" in updates:
            if not any(ch.isdigit() for ch in updates["mobile_number"]):
                raise ConflictException("Enter a valid mobile number.")
            duplicate = await self.customer_repo.get_by_mobile_excluding(
                updates["mobile_number"], customer.id
            )
            if duplicate:
                raise ConflictException(
                    "Another customer is already registered with this mobile number.",
                    error_code="DUPLICATE_CUSTOMER_MOBILE",
                )
        if updates:
            await self.customer_repo.update(customer, **updates)
        return self._to_dict(customer)

    async def get_customer_ledger(self, customer_id: UUID) -> dict:
        customer = await self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundException("Customer", customer_id)

        from app.repositories.finance_repo import FinanceAccountRepository
        from app.repositories.chitti_repo import ChittiMemberRepository, ChittiRepository
        from sqlalchemy import select

        from app.models.chitti import Chitti, ChittiMember, ChittiTransaction
        from app.models.finance import FinanceAccount, FinanceSchedule
        from app.models.payment import PaymentTransaction

        finance_repo = FinanceAccountRepository(self.session)
        member_repo = ChittiMemberRepository(self.session)
        chitti_repo = ChittiRepository(self.session)

        finance_accounts = await finance_repo.get_by_customer_id(customer_id)
        memberships = await member_repo.get_by_customer_id(customer_id)
        chitti_list = []
        for m in memberships:
            chitti = await chitti_repo.get_by_id(m.chitti_id)
            if chitti:
                chitti_list.append({
                    "id": str(chitti.id),
                    "chitti_code": chitti.chitti_code,
                    "name": chitti.name,
                    "status": chitti.status,
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
            select(ChittiTransaction, Chitti.name)
            .join(ChittiMember, ChittiMember.id == ChittiTransaction.member_id)
            .join(Chitti, Chitti.id == ChittiTransaction.chitti_id)
            .where(
                ChittiMember.customer_id == customer_id,
                ChittiTransaction.transaction_type.in_(("CONTRIBUTION", "REVERSAL")),
            )
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
        for transaction, chitti_name in chitti_rows:
            is_reversal = transaction.transaction_type == "REVERSAL"
            chitti_history.append({
                "id": str(transaction.id),
                "transaction_id": f"CHT-{transaction.id}",
                "source": "CHITTI",
                "customer_name": customer.full_name,
                "account_name": chitti_name,
                "period_number": transaction.period_number,
                "amount": float(transaction.amount),
                "payment_method": transaction.payment_method,
                "payment_date": str(transaction.payment_date) if transaction.payment_date else None,
                "status": "REVERSED" if is_reversal else "COMPLETED",
                "is_reversal": is_reversal,
                "reversal_of_transaction_id": None,
                "reversed_by_transaction_id": None,
                "created_at": transaction.created_at,
                "_notes": transaction.notes,
            })
        chitti_by_id = {str(row[0].id): row[0] for row in chitti_rows}
        chitti_item_by_id = {item["id"]: item for item in chitti_history}
        for item in chitti_history:
            transaction = chitti_by_id[item["id"]]
            if item["is_reversal"] and transaction.notes:
                # Existing Chitti reversals record the original UUID in their
                # immutable notes ("Reversal of <uuid>: ...").
                original_id = transaction.notes.partition(":")[0].removeprefix("Reversal of ")
                original_item = chitti_item_by_id.get(original_id)
                if original_item:
                    item["reversal_of_transaction_id"] = f"CHT-{original_id}"
                    original_item["status"] = "REVERSED"
                    original_item["reversed_by_transaction_id"] = item["transaction_id"]
            item.pop("_notes", None)

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
