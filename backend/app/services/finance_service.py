"""
Finance account management service.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models.customer import Customer
from app.models.finance import FinanceAgreement
from app.repositories.finance_repo import FinanceAccountRepository, FinanceScheduleRepository
from app.services.audit_service import AuditService
from app.services.finance_terms import compute_finance_terms_hash
from app.utils.codes import generate_finance_code


class FinanceService:
    """Finance account CRUD and schedule generation."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.account_repo = FinanceAccountRepository(session)
        self.schedule_repo = FinanceScheduleRepository(session)

    @staticmethod
    def _customer_summary(customer: Customer) -> dict:
        """Customer identity needed by Finance screens, without exposing the whole record."""
        return {
            "customer_name": customer.full_name,
            "customer_code": customer.customer_code,
            "mobile_number": customer.mobile_number,
        }

    async def _agreement_statuses(self, account_ids) -> dict:
        """Map finance account IDs to linked agreement status (NONE if absent)."""
        ids = list(account_ids)
        if not ids:
            return {}
        result = await self.session.execute(
            select(
                FinanceAgreement.finance_account_id,
                FinanceAgreement.agreement_status,
            ).where(FinanceAgreement.finance_account_id.in_(ids))
        )
        return {row[0]: row[1] for row in result.all()}

    async def create_account(
        self,
        *,
        agreement_id: str,
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
        customer_uuid = UUID(customer_id)
        customer = await self.session.get(Customer, customer_uuid)
        if not customer:
            raise NotFoundException("Customer", customer_id)

        # Agreement enforcement happens before any account/schedule row is
        # created. Printing alone is never enough — the agreement must be
        # CONFIRMED and its hash must match these exact submitted loan fields.
        try:
            agreement_uuid = UUID(str(agreement_id))
        except (ValueError, TypeError):
            raise BadRequestException(
                "A valid confirmed finance agreement is required.",
                error_code="AGREEMENT_REQUIRED",
            )
        agreement = await self.session.get(FinanceAgreement, agreement_uuid)
        if not agreement:
            raise BadRequestException(
                "A confirmed finance agreement is required before creating an account.",
                error_code="AGREEMENT_REQUIRED",
            )
        if str(agreement.customer_id) != str(customer_uuid):
            raise BadRequestException(
                "The agreement belongs to a different customer.",
                error_code="AGREEMENT_CUSTOMER_MISMATCH",
            )
        expected_hash = compute_finance_terms_hash(
            {
                "customer_id": customer_id,
                "principal_amount": principal_amount,
                "interest_rate": interest_rate,
                "interest_type": interest_type,
                "fees": fees,
                "frequency": frequency,
                "start_date": start_date,
                "first_due_date": first_due_date,
                "number_of_installments": number_of_installments,
                "custom_installment_amount": custom_installment_amount,
            }
        )
        if agreement.terms_hash != expected_hash:
            raise BadRequestException(
                "Loan terms do not match the signed agreement.",
                error_code="AGREEMENT_TERMS_MISMATCH",
            )
        if agreement.agreement_status != "CONFIRMED":
            raise BadRequestException(
                "The agreement must be confirmed before an account can be created.",
                error_code="AGREEMENT_NOT_CONFIRMED",
            )
        if agreement.finance_account_id is not None:
            raise BadRequestException(
                "This agreement has already been used to create a finance account.",
                error_code="AGREEMENT_ALREADY_USED",
            )

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
            customer_id=customer_uuid,
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

        # Consume the agreement exactly once. No disbursement state is created:
        # accounts remain ACTIVE as before and disbursement is a later step.
        agreement.finance_account_id = account.id
        await self.session.flush()
        await AuditService(self.session).log(
            user_id=created_by,
            action="FINANCE_AGREEMENT_CONSUMED",
            entity_type="FINANCE_AGREEMENT",
            entity_id=agreement.id,
            previous_value={"status": "CONFIRMED", "finance_account_id": None},
            new_value={
                "status": "CONFIRMED",
                "finance_account_id": str(account.id),
                "agreement_id": str(agreement.id),
                "account_number": account.account_number,
            },
        )

        return {
            "id": str(account.id),
            "account_number": account.account_number,
            "customer_id": str(account.customer_id),
            **self._customer_summary(customer),
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
            "agreement_id": str(agreement.id),
            "agreement_status": agreement.agreement_status,
            "notes": account.notes,
            "created_at": str(account.created_at),
            "updated_at": str(account.updated_at),
        }

    async def get_account(self, account_id: UUID) -> dict:
        """Get a finance account by ID with its customer identity."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise NotFoundException("Finance account", account_id)

        customer_summary = (
            self._customer_summary(account.customer)
            if account.customer
            else {"customer_name": None, "customer_code": None, "mobile_number": None}
        )
        statuses = await self._agreement_statuses([account.id])
        return {
            "id": str(account.id),
            "account_number": account.account_number,
            "customer_id": str(account.customer_id),
            **customer_summary,
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
            "agreement_status": statuses.get(account.id, "NONE"),
            "notes": account.notes,
            "created_at": str(account.created_at),
            "updated_at": str(account.updated_at),
        }

    async def update_account(
        self,
        account_id: UUID,
        *,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        updated_by: Optional[UUID] = None,
    ) -> dict:
        """Update editable finance-account metadata.

        Only administrative metadata is accepted here. Financial totals,
        schedules and allocation state are deliberately untouched so an edit
        cannot silently rewrite repayment history.
        """
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise NotFoundException("Finance account", account_id)

        previous_value = {
            "status": account.status,
            "notes": account.notes,
        }

        changes: dict[str, object] = {}
        if status is not None:
            changes["status"] = status
        if notes is not None:
            changes["notes"] = notes

        if changes:
            await self.account_repo.update(account, **changes)
            await AuditService(self.session).log(
                user_id=updated_by,
                action="FINANCE_UPDATED",
                entity_type="FINANCE_ACCOUNT",
                entity_id=account.id,
                previous_value=previous_value,
                new_value={
                    "status": account.status,
                    "notes": account.notes,
                },
            )

        return await self.get_account(account_id)

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
        customer_id: Optional[UUID] = None,
        search: Optional[str] = None,
        agreement_status: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """List finance accounts with pagination, customer identity and agreement state."""
        filters = {}
        if status:
            filters["status"] = status
        if customer_id:
            filters["customer_id"] = customer_id

        skip = (page - 1) * per_page
        accounts, total = await self.account_repo.list_with_customer(
            skip=skip,
            limit=per_page,
            filters=filters,
            search=search,
            agreement_status=agreement_status,
        )

        statuses = await self._agreement_statuses([a.id for a, _ in accounts])
        items = [
            {
                "id": str(a.id),
                "account_number": a.account_number,
                "customer_id": str(a.customer_id),
                **self._customer_summary(customer),
                "principal_amount": float(a.principal_amount),
                "interest_rate": float(a.interest_rate),
                "interest_type": a.interest_type,
                "fees": float(a.fees),
                "total_payable": float(a.total_payable),
                "installment_amount": float(a.installment_amount),
                "frequency": a.frequency,
                "status": a.status,
                "agreement_status": statuses.get(a.id, "NONE"),
                "start_date": str(a.start_date),
                "first_due_date": str(a.first_due_date),
                "number_of_installments": a.number_of_installments,
                "notes": a.notes,
                "created_at": str(a.created_at),
                "updated_at": str(a.updated_at),
            }
            for a, customer in accounts
        ]
        return items, total
