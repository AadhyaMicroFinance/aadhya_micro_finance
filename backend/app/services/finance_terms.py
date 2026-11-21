"""Canonical loan-term hashing shared by agreement generation and consumption.

The hash is deliberately computed from a small, explicit set of loan fields.
Both the agreement service (at generation) and the account service (at
creation) call this module independently, so changing any term after the
customer signed the document always produces a mismatch.
"""

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

CENT = Decimal("0.01")


def _money(value) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))


def _date(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def canonical_loan_terms(loan: dict) -> dict:
    """Normalise loan fields into a stable JSON-serialisable payload.

    ``1000``, ``1000.0`` and ``Decimal("1000.00")`` all hash the same; dates
    and UUIDs are stringified. Notes are intentionally excluded — they are not
    a financial term and editing them must not invalidate a signed agreement.
    """
    return {
        "customer_id": str(UUID(str(loan["customer_id"]))),
        "principal_amount": _money(loan["principal_amount"]),
        "interest_rate": _money(loan.get("interest_rate", Decimal("0"))),
        "interest_type": str(loan.get("interest_type", "FLAT")).upper(),
        "fees": _money(loan.get("fees", Decimal("0"))),
        "frequency": str(loan["frequency"]).upper(),
        "start_date": _date(loan["start_date"]),
        "first_due_date": _date(loan["first_due_date"]),
        "number_of_installments": int(loan["number_of_installments"]),
        "custom_installment_amount": _money(loan.get("custom_installment_amount")),
    }


def compute_finance_terms_hash(loan: dict) -> str:
    """Deterministic SHA-256 over the canonical customer id + loan fields."""
    canonical = canonical_loan_terms(loan)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
