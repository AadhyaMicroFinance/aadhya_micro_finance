"""
Finance account management service.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.repositories.finance_repo import FinanceAccountRepository, FinanceScheduleRepository
from app.utils.codes import generate_finance_code


class FinanceService:
    """Finance account CRUD and schedule generation."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.account_repo = FinanceAccountRepository(session)
        self.schedule_repo = FinanceScheduleRepository(session)

    async def create_account(
        self,
        *,
        customer_id: str,
        principal_amount: Decimal,
        interest_rate: Decimal = Decimal("0"),
        interest_type: str = "FLAT",
        fees: Decimal = Decimal("0"),
        frequency: str,
        start_date,
        first_due_date,
        number_of_installments: int,
        custom_installment_amount: Optional[Decimal] = None,
        notes: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> dict:
        """Create a finance account and generate its payment schedule."""
        from app.services.calculation_engine import CalculationEngine
        from datetime import date

        calc = CalculationEngine()

        # Calculate total payable and installment amount
        total_payable, installment_amount = calc.calculate_finance_totals(
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            interest_type=interest_type,
            fees=fees,
            number_of_installments=number_of_installments,
            custom_installment_amount=custom_installment_amount,
        )

        account_number = await generate_finance_code(self.session)

        account = await self.account_repo.create(
            account_number=account_number,
            customer_id=UUID(customer_id),
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            interest_type=interest_type,
            fees=fees,
            total_payable=total_payable,
            installment_amount=installment_amount,
            custom_installment_amount=custom_installment_amount,
            frequency=frequency,
            start_date=start_date,
            first_due_date=first_due_date,
            number_of_installments=number_of_installments,
            status="ACTIVE",
            notes=notes,
            created_by=created_by,
        )

        # Generate payment schedule
        schedule = calc.generate_schedule(
            account_id=account.id,
            installment_amount=installment_amount,
            first_due_date=first_due_date,
            number_of_installments=number_of_installments,
            frequency=frequency,
        )
        for entry in schedule:
            await self.schedule_repo.create(**entry)

        return {
            "id": str(account.id),
            "account_number": account.account_number,
            "customer_id": str(account.customer_id),
            "principal_amount": float(account.principal_amount),
            "interest_rate": float(account.interest_rate),
            "interest_type": account.interest_type,
            "fees": float(account.fees),
            "total_payable": float(account.total_payable),
            "installment_amount": float(account.installment_amount),
            "frequency": account.frequency,
            "start_date": str(account.start_date),
            "first_due_date": str(account.first_due_date),
            "number_of_installments": account.number_of_installments,
            "status": account.status,
            "notes": account.notes,
            "created_at": str(account.created_at),
            "updated_at": str(account.updated_at),
        }

    async def get_account(self, account_id: UUID) -> dict:
        """Get a finance account by ID with schedule."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise NotFoundException("Finance account", account_id)

        return {
            "id": str(account.id),
            "account_number": account.account_number,
            "customer_id": str(account.customer_id),
            "principal_amount": float(account.principal_amount),
            "interest_rate": float(account.interest_rate),
            "interest_type": account.interest_type,
            "fees": float(account.fees),
            "total_payable": float(account.total_payable),
            "installment_amount": float(account.installment_amount),
            "frequency": account.frequency,
            "start_date": str(account.start_date),
            "first_due_date": str(account.first_due_date),
            "number_of_installments": account.number_of_installments,
            "status": account.status,
            "notes": account.notes,
            "created_at": str(account.created_at),
            "updated_at": str(account.updated_at),
        }

    async def get_schedule(self, account_id: UUID) -> list[dict]:
        """Get the payment schedule for an account."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise NotFoundException("Finance account", account_id)

        schedules = await self.schedule_repo.get_by_finance_account_id(account_id)
        return [
            {
                "id": str(s.id),
                "installment_number": s.installment_number,
                "due_date": str(s.due_date),
                "expected_amount": float(s.expected_amount),
                "paid_amount": float(s.paid_amount),
                "remaining_amount": float(s.remaining_amount),
                "status": s.status,
            }
            for s in schedules
        ]

    async def list_accounts(
        self,
        page: int = 1,
        per_page: int = 25,
        status: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """List finance accounts with pagination."""
        filters = {}
        if status:
            filters["status"] = status
        if customer_id:
            filters["customer_id"] = UUID(customer_id)

        skip = (page - 1) * per_page
        accounts, total = await self.account_repo.get_all(
            skip=skip, limit=per_page, filters=filters
        )

        items = [
            {
                "id": str(a.id),
                "account_number": a.account_number,
                "customer_id": str(a.customer_id),
                "principal_amount": float(a.principal_amount),
                "total_payable": float(a.total_payable),
                "installment_amount": float(a.installment_amount),
                "frequency": a.frequency,
                "status": a.status,
                "start_date": str(a.start_date),
                "first_due_date": str(a.first_due_date),
                "number_of_installments": a.number_of_installments,
                "created_at": str(a.created_at),
            }
            for a in accounts
        ]
        return items, total
