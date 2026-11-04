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
        if updates:
            await self.customer_repo.update(customer, **updates)
        return self._to_dict(customer)

    async def get_customer_ledger(self, customer_id: UUID) -> dict:
        customer = await self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundException("Customer", customer_id)

        from app.repositories.finance_repo import FinanceAccountRepository
        from app.repositories.chitti_repo import ChittiMemberRepository, ChittiRepository
        from app.repositories.payment_repo import PaymentRepository

        finance_repo = FinanceAccountRepository(self.session)
        member_repo = ChittiMemberRepository(self.session)
        chitti_repo = ChittiRepository(self.session)
        payment_repo = PaymentRepository(self.session)

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
        payments = await payment_repo.get_by_customer_id(customer_id)

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
            "payment_history": [
                {
                    "id": str(p.id),
                    "transaction_id": p.transaction_id,
                    "amount": float(p.amount),
                    "payment_method": p.payment_method,
                    "payment_date": str(p.payment_date),
                    "status": p.status,
                }
                for p in payments
            ],
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
