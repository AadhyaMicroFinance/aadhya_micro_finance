"""Finance loan agreement workflow: generate → print → confirm.

The agreement is an immutable snapshot of the customer and loan terms. It never
creates a Finance account and never activates one: account creation is a
separate endpoint that independently validates a CONFIRMED agreement.
"""

import html
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.customer import Customer
from app.models.finance import FinanceAgreement
from app.services.audit_service import AuditService
from app.services.calculation_engine import CalculationEngine
from app.services.finance_terms import compute_finance_terms_hash
from app.utils.timezone import now_ist, today_ist

CONFIRMATION_TEXT = "I confirm that the agreement has been signed by the customer."


class FinanceAgreementService:
    """Generate, review, print, download and confirm Finance agreements."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    async def generate_agreement(self, loan: dict, *, created_by: Optional[UUID] = None) -> dict:
        """Generate a Finance agreement and its immutable terms snapshot."""
        customer_uuid = UUID(str(loan["customer_id"]))
        customer = await self.session.get(Customer, customer_uuid)
        if not customer:
            raise NotFoundException("Customer", loan["customer_id"])

        loan_fields = {
            "customer_id": str(customer_uuid),
            "principal_amount": loan["principal_amount"],
            "interest_rate": loan.get("interest_rate", Decimal("0")),
            "interest_type": loan.get("interest_type", "FLAT"),
            "fees": loan.get("fees", Decimal("0")),
            "frequency": loan["frequency"],
            "start_date": loan["start_date"],
            "first_due_date": loan["first_due_date"],
            "number_of_installments": loan["number_of_installments"],
            "custom_installment_amount": loan.get("custom_installment_amount"),
        }

        # The existing calculation and schedule generators are the single
        # source of truth for every term shown in the document.
        calc = CalculationEngine()
        total_payable, installment_amount = calc.calculate_finance_totals(
            principal_amount=loan_fields["principal_amount"],
            interest_rate=loan_fields["interest_rate"],
            interest_type=loan_fields["interest_type"],
            fees=loan_fields["fees"],
            number_of_installments=loan_fields["number_of_installments"],
            custom_installment_amount=loan_fields["custom_installment_amount"],
        )
        schedule = calc.generate_schedule(
            account_id=None,
            installment_amount=installment_amount,
            first_due_date=loan_fields["first_due_date"],
            number_of_installments=loan_fields["number_of_installments"],
            frequency=loan_fields["frequency"],
        )

        canonical = compute_finance_terms_hash(loan_fields)
        agreement_number = f"FAGR-{today_ist().year}-{uuid4().int % 10**12:012d}"
        snapshot = {
            "agreement_number": agreement_number,
            "agreement_date": str(today_ist()),
            "customer": {
                "id": str(customer.id),
                "full_name": customer.full_name,
                "customer_code": customer.customer_code,
                "mobile_number": customer.mobile_number,
                "address": customer.address,
            },
            "loan": {
                "customer_id": str(customer.id),
                "principal_amount": str(loan_fields["principal_amount"]),
                "interest_rate": str(loan_fields["interest_rate"]),
                "interest_type": loan_fields["interest_type"],
                "fees": str(loan_fields["fees"]),
                "frequency": loan_fields["frequency"],
                "start_date": str(loan_fields["start_date"]),
                "first_due_date": str(loan_fields["first_due_date"]),
                "number_of_installments": int(loan_fields["number_of_installments"]),
                "custom_installment_amount": (
                    str(loan_fields["custom_installment_amount"])
                    if loan_fields["custom_installment_amount"] is not None
                    else None
                ),
            },
            "terms": {
                "principal_amount": str(loan_fields["principal_amount"]),
                "interest_rate": str(loan_fields["interest_rate"]),
                "interest_type": loan_fields["interest_type"],
                "fees": str(loan_fields["fees"]),
                "frequency": loan_fields["frequency"],
                "start_date": str(loan_fields["start_date"]),
                "first_due_date": str(loan_fields["first_due_date"]),
                "number_of_installments": int(loan_fields["number_of_installments"]),
                "custom_installment_amount": (
                    str(loan_fields["custom_installment_amount"])
                    if loan_fields["custom_installment_amount"] is not None
                    else None
                ),
                "interest_amount": str(total_payable - loan_fields["principal_amount"] - loan_fields["fees"]),
                "total_payable": str(total_payable),
                "installment_amount": str(installment_amount),
            },
            "schedule": [
                {
                    "installment_number": int(entry["installment_number"]),
                    "due_date": str(entry["due_date"]),
                    "expected_amount": str(entry["expected_amount"]),
                }
                for entry in schedule
            ],
            "terms_hash": canonical,
        }

        agreement = FinanceAgreement(
            agreement_number=agreement_number,
            customer_id=customer.id,
            agreement_status="GENERATED",
            agreement_snapshot=snapshot,
            terms_hash=canonical,
            generated_at=now_ist(),
            print_count=0,
        )
        self.session.add(agreement)
        await self.session.flush()

        await AuditService(self.session).log(
            user_id=created_by,
            action="FINANCE_AGREEMENT_GENERATED",
            entity_type="FINANCE_AGREEMENT",
            entity_id=agreement.id,
            new_value={"agreement_number": agreement_number, "terms_hash": canonical},
        )
        await self.session.commit()
        return self._agreement_to_dict(agreement)

    # ------------------------------------------------------------------
    # Read / review
    # ------------------------------------------------------------------
    async def get_agreement(self, agreement_id: UUID) -> dict:
        agreement = await self._get(agreement_id)
        return self._agreement_to_dict(agreement)

    async def download_agreement(self, agreement_id: UUID) -> dict:
        """Return the document for download without changing agreement state."""
        agreement = await self._get(agreement_id)
        data = self._agreement_to_dict(agreement)
        return {
            "filename": f"{agreement.agreement_number}.html",
            "content_type": "text/html; charset=utf-8",
            "content": data["agreement_html"],
        }

    # ------------------------------------------------------------------
    # Print
    # ------------------------------------------------------------------
    async def print_agreement(self, agreement_id: UUID, *, created_by: Optional[UUID] = None) -> dict:
        agreement = await self._get(agreement_id)
        # A signed (CONFIRMED) agreement may still be printed or reprinted;
        # printing never downgrades its status.
        if agreement.agreement_status not in ("GENERATED", "PRINTED", "CONFIRMED"):
            raise BadRequestException(
                f"Cannot print agreement with status {agreement.agreement_status}.",
                error_code="AGREEMENT_NOT_PRINTABLE",
            )

        now = now_ist()
        agreement.print_count = (agreement.print_count or 0) + 1
        if agreement.printed_at is None:
            agreement.printed_at = now
        if agreement.agreement_status != "CONFIRMED":
            agreement.agreement_status = "PRINTED"
        await self.session.flush()

        await AuditService(self.session).log(
            user_id=created_by,
            action="FINANCE_AGREEMENT_PRINTED",
            entity_type="FINANCE_AGREEMENT",
            entity_id=agreement.id,
            new_value={"print_count": agreement.print_count, "printed_at": str(agreement.printed_at)},
        )
        await self.session.commit()
        return self._agreement_to_dict(agreement)

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------
    async def confirm_agreement(
        self,
        agreement_id: UUID,
        *,
        confirmation_text: str,
        confirmed_by: Optional[UUID] = None,
    ) -> dict:
        """Mark an agreement CONFIRMED after the exact signed confirmation."""
        if confirmation_text != CONFIRMATION_TEXT:
            raise BadRequestException(
                "Confirmation text must exactly match: " + CONFIRMATION_TEXT,
                error_code="AGREEMENT_CONFIRMATION_TEXT_MISMATCH",
            )

        agreement = await self._get(agreement_id)
        if agreement.agreement_status == "CONFIRMED":
            raise BadRequestException(
                "This agreement has already been confirmed.",
                error_code="AGREEMENT_ALREADY_CONFIRMED",
            )
        if agreement.agreement_status not in ("GENERATED", "PRINTED"):
            raise BadRequestException(
                f"Cannot confirm agreement with status {agreement.agreement_status}.",
                error_code="AGREEMENT_NOT_CONFIRMABLE",
            )

        agreement.agreement_status = "CONFIRMED"
        agreement.confirmed_at = now_ist()
        agreement.confirmed_by = confirmed_by
        await self.session.flush()

        await AuditService(self.session).log(
            user_id=confirmed_by,
            action="FINANCE_AGREEMENT_CONFIRMED",
            entity_type="FINANCE_AGREEMENT",
            entity_id=agreement.id,
            new_value={
                "status": "CONFIRMED",
                "confirmed_at": str(agreement.confirmed_at),
                "confirmed_by": str(confirmed_by) if confirmed_by else None,
            },
        )
        await self.session.commit()
        return self._agreement_to_dict(agreement)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _get(self, agreement_id: UUID) -> FinanceAgreement:
        agreement = await self.session.get(FinanceAgreement, UUID(str(agreement_id)))
        if not agreement:
            raise NotFoundException("Finance agreement", agreement_id)
        return agreement

    @staticmethod
    def _number(value, default=None):
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _agreement_to_dict(self, agreement: FinanceAgreement) -> dict:
        snapshot = agreement.agreement_snapshot or {}
        customer = snapshot.get("customer", {})
        loan = snapshot.get("loan", {})
        terms = snapshot.get("terms", {})
        schedule = snapshot.get("schedule", [])
        html_text = self._render_html(agreement.agreement_number, customer, loan, terms, schedule)
        plain_text = self._render_text(agreement.agreement_number, customer, loan, terms, schedule)

        response_terms = {
            "principal_amount": self._number(terms.get("principal_amount"), 0.0),
            "interest_rate": self._number(terms.get("interest_rate"), 0.0),
            "interest_type": terms.get("interest_type"),
            "fees": self._number(terms.get("fees"), 0.0),
            "frequency": terms.get("frequency"),
            "start_date": terms.get("start_date"),
            "first_due_date": terms.get("first_due_date"),
            "number_of_installments": terms.get("number_of_installments"),
            "custom_installment_amount": self._number(terms.get("custom_installment_amount")),
            "interest_amount": self._number(terms.get("interest_amount"), 0.0),
            "total_payable": self._number(terms.get("total_payable"), 0.0),
            "installment_amount": self._number(terms.get("installment_amount"), 0.0),
        }
        response_schedule = [
            {
                "installment_number": entry.get("installment_number"),
                "due_date": entry.get("due_date"),
                "expected_amount": self._number(entry.get("expected_amount"), 0.0),
            }
            for entry in schedule
        ]
        return {
            "agreement_id": str(agreement.id),
            "agreement_number": agreement.agreement_number,
            "agreement_html": html_text,
            "agreement_text": plain_text,
            "customer_name": customer.get("full_name"),
            "customer_code": customer.get("customer_code"),
            "mobile_number": customer.get("mobile_number"),
            "terms": response_terms,
            "schedule": response_schedule,
            "generated_at": str(agreement.generated_at) if agreement.generated_at else None,
            "status": agreement.agreement_status,
            "agreement_status": agreement.agreement_status,
            "print_count": agreement.print_count,
            "printed_at": str(agreement.printed_at) if agreement.printed_at else None,
            "confirmed_at": str(agreement.confirmed_at) if agreement.confirmed_at else None,
            "confirmed_by": str(agreement.confirmed_by) if agreement.confirmed_by else None,
            "terms_hash": agreement.terms_hash,
            "agreement_snapshot": snapshot,
        }

    @staticmethod
    def _render_html(number: str, customer: dict, loan: dict, terms: dict, schedule: list) -> str:
        esc = lambda value: html.escape("" if value is None else str(value))
        rows = "".join(
            "<tr><td>{n}</td><td>{d}</td><td>{a}</td></tr>".format(
                n=esc(entry.get("installment_number")),
                d=esc(entry.get("due_date")),
                a=esc(entry.get("expected_amount")),
            )
            for entry in schedule
        )
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Finance Loan Agreement {number}</title></head><body>"
            "<h1>Finance Loan Agreement</h1>"
            "<p>Agreement Number: {number}</p>"
            "<h2>Customer</h2>"
            "<p>Name: {name}<br>Customer Code: {code}<br>Mobile Number: {mobile}</p>"
            "<h2>Loan Terms</h2>"
            "<table border='1' cellpadding='4'>"
            "<tr><th>Field</th><th>Value</th></tr>"
            "<tr><td>Customer ID</td><td>{cid}</td></tr>"
            "<tr><td>Principal Amount</td><td>{principal}</td></tr>"
            "<tr><td>Interest Rate</td><td>{rate}</td></tr>"
            "<tr><td>Interest Type</td><td>{itype}</td></tr>"
            "<tr><td>Fees</td><td>{fees}</td></tr>"
            "<tr><td>Frequency</td><td>{frequency}</td></tr>"
            "<tr><td>Start Date</td><td>{start}</td></tr>"
            "<tr><td>First Due Date</td><td>{first_due}</td></tr>"
            "<tr><td>Number of Installments</td><td>{count}</td></tr>"
            "<tr><td>Custom Installment Amount</td><td>{custom}</td></tr>"
            "<tr><td>Total Payable</td><td>{total}</td></tr>"
            "<tr><td>Installment Amount</td><td>{installment}</td></tr>"
            "</table>"
            "<h2>Repayment Schedule</h2>"
            "<table border='1' cellpadding='4'>"
            "<tr><th>Installment Number</th><th>Due Date</th><th>Expected Amount</th></tr>"
            "{rows}</table>"
            "<p>Customer signature: ____________________</p>"
            "</body></html>"
        ).format(
            number=esc(number),
            name=esc(customer.get("full_name")),
            code=esc(customer.get("customer_code")),
            mobile=esc(customer.get("mobile_number")),
            cid=esc(loan.get("customer_id")),
            principal=esc(loan.get("principal_amount")),
            rate=esc(loan.get("interest_rate")),
            itype=esc(loan.get("interest_type")),
            fees=esc(loan.get("fees")),
            frequency=esc(loan.get("frequency")),
            start=esc(loan.get("start_date")),
            first_due=esc(loan.get("first_due_date")),
            count=esc(loan.get("number_of_installments")),
            custom=esc(loan.get("custom_installment_amount") or "N/A"),
            total=esc(terms.get("total_payable")),
            installment=esc(terms.get("installment_amount")),
            rows=rows,
        )

    @staticmethod
    def _render_text(number: str, customer: dict, loan: dict, terms: dict, schedule: list) -> str:
        def value(key, source=loan):
            return "" if source.get(key) is None else str(source.get(key))

        lines = [
            "FINANCE LOAN AGREEMENT",
            f"Agreement Number: {number}",
            "",
            "CUSTOMER",
            f"Name: {value('full_name', customer)}",
            f"Customer Code: {value('customer_code', customer)}",
            f"Mobile Number: {value('mobile_number', customer)}",
            "",
            "LOAN TERMS",
            f"Customer ID: {value('customer_id')}",
            f"Principal Amount: {value('principal_amount')}",
            f"Interest Rate: {value('interest_rate')}",
            f"Interest Type: {value('interest_type')}",
            f"Fees: {value('fees')}",
            f"Frequency: {value('frequency')}",
            f"Start Date: {value('start_date')}",
            f"First Due Date: {value('first_due_date')}",
            f"Number of Installments: {value('number_of_installments')}",
            f"Custom Installment Amount: {value('custom_installment_amount', terms) or 'N/A'}",
            f"Total Payable: {value('total_payable', terms)}",
            f"Installment Amount: {value('installment_amount', terms)}",
            "",
            "REPAYMENT SCHEDULE",
            "Installment Number | Due Date | Expected Amount",
        ]
        lines.extend(
            f"{entry.get('installment_number')} | {entry.get('due_date')} | {entry.get('expected_amount')}"
            for entry in schedule
        )
        lines.extend(["", "Customer signature: ____________________"])
        return "\n".join(lines)
