"""
Tests for the Financial Calculation Engine.

These tests verify correctness of monetary calculations.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta

from app.services.calculation_engine import CalculationEngine


@pytest.fixture
def calc():
    return CalculationEngine()


class TestCalculateFinanceTotals:
    """Test finance total calculations."""

    def test_simple_no_interest(self, calc):
        """₹50,000 principal, 0% interest, 10 installments."""
        total, installment = calc.calculate_finance_totals(
            principal_amount=Decimal("50000"),
            interest_rate=Decimal("0"),
            interest_type="FLAT",
            fees=Decimal("0"),
            number_of_installments=10,
        )
        assert total == Decimal("50000.00")
        assert installment == Decimal("5000.00")

    def test_flat_interest(self, calc):
        """₹50,000 principal, 12% flat interest, 10 installments."""
        total, installment = calc.calculate_finance_totals(
            principal_amount=Decimal("50000"),
            interest_rate=Decimal("12"),
            interest_type="FLAT",
            fees=Decimal("0"),
            number_of_installments=10,
        )
        # Interest = 50000 * 0.12 = 6000
        assert total == Decimal("56000.00")
        assert installment == Decimal("5600.00")

    def test_flat_interest_with_fees(self, calc):
        """₹50,000 principal, 12% flat, ₹500 fees, 10 installments."""
        total, installment = calc.calculate_finance_totals(
            principal_amount=Decimal("50000"),
            interest_rate=Decimal("12"),
            interest_type="FLAT",
            fees=Decimal("500"),
            number_of_installments=10,
        )
        assert total == Decimal("56500.00")
        assert installment == Decimal("5650.00")

    def test_reducing_interest(self, calc):
        """₹50,000 principal, 12% reducing, 10 installments."""
        total, installment = calc.calculate_finance_totals(
            principal_amount=Decimal("50000"),
            interest_rate=Decimal("12"),
            interest_type="REDUCING",
            fees=Decimal("0"),
            number_of_installments=10,
        )
        # Reducing approximation: 50000 * 0.12 / 2 = 3000
        assert total == Decimal("53000.00")
        assert installment == Decimal("5300.00")

    def test_custom_installment_amount(self, calc):
        """Custom installment overrides auto-calculation."""
        total, installment = calc.calculate_finance_totals(
            principal_amount=Decimal("50000"),
            interest_rate=Decimal("0"),
            interest_type="FLAT",
            fees=Decimal("0"),
            number_of_installments=10,
            custom_installment_amount=Decimal("6000"),
        )
        assert total == Decimal("50000.00")
        assert installment == Decimal("6000.00")

    def test_monthly_schedule_dates(self, calc):
        """Schedule due dates should be 30 days apart for monthly."""
        schedule = calc.generate_schedule(
            account_id="test-id",
            installment_amount=Decimal("5000"),
            first_due_date=date(2026, 9, 1),
            number_of_installments=3,
            frequency="MONTHLY",
        )
        assert len(schedule) == 3
        assert schedule[0]["due_date"] == date(2026, 9, 1)
        assert schedule[1]["due_date"] == date(2026, 10, 1)
        assert schedule[2]["due_date"] == date(2026, 10, 31)

    def test_weekly_schedule_dates(self, calc):
        """Schedule due dates should be 7 days apart for weekly."""
        schedule = calc.generate_schedule(
            account_id="test-id",
            installment_amount=Decimal("1000"),
            first_due_date=date(2026, 9, 1),
            number_of_installments=4,
            frequency="WEEKLY",
        )
        assert len(schedule) == 4
        assert schedule[0]["due_date"] == date(2026, 9, 1)
        assert schedule[1]["due_date"] == date(2026, 9, 8)
        assert schedule[2]["due_date"] == date(2026, 9, 15)
        assert schedule[3]["due_date"] == date(2026, 9, 22)


class TestPaymentAllocation:
    """Test payment allocation across installments."""

    def test_exact_payment(self, calc):
        """Payment exactly covers one installment."""
        from unittest.mock import MagicMock

        schedule1 = MagicMock()
        schedule1.id = "s1"
        schedule1.remaining_amount = Decimal("5000")
        schedule1.status = "DUE"

        allocations = calc.allocate_payment(
            Decimal("5000"), [schedule1], "AUTO_ALLOCATE"
        )
        assert len(allocations) == 1
        assert allocations[0]["allocated_amount"] == Decimal("5000")

    def test_underpayment(self, calc):
        """Payment is less than one installment."""
        from unittest.mock import MagicMock

        schedule1 = MagicMock()
        schedule1.id = "s1"
        schedule1.remaining_amount = Decimal("5000")
        schedule1.status = "DUE"

        allocations = calc.allocate_payment(
            Decimal("3000"), [schedule1], "AUTO_ALLOCATE"
        )
        assert len(allocations) == 1
        assert allocations[0]["allocated_amount"] == Decimal("3000")

    def test_overpayment_spreads(self, calc):
        """Payment covers multiple installments."""
        from unittest.mock import MagicMock

        schedule1 = MagicMock()
        schedule1.id = "s1"
        schedule1.remaining_amount = Decimal("5000")
        schedule1.status = "DUE"

        schedule2 = MagicMock()
        schedule2.id = "s2"
        schedule2.remaining_amount = Decimal("5000")
        schedule2.status = "UPCOMING"

        allocations = calc.allocate_payment(
            Decimal("7000"), [schedule1, schedule2], "AUTO_ALLOCATE"
        )
        assert len(allocations) == 2
        assert allocations[0]["allocated_amount"] == Decimal("5000")
        assert allocations[1]["allocated_amount"] == Decimal("2000")

    def test_advance_payment(self, calc):
        """Payment exceeds all installments — creates advance credit."""
        from unittest.mock import MagicMock

        schedule1 = MagicMock()
        schedule1.id = "s1"
        schedule1.remaining_amount = Decimal("5000")
        schedule1.status = "DUE"

        allocations = calc.allocate_payment(
            Decimal("8000"), [schedule1], "AUTO_ALLOCATE"
        )
        assert len(allocations) == 2
        assert allocations[0]["allocated_amount"] == Decimal("5000")
        assert allocations[1].get("is_advance") is True
        assert allocations[1]["allocated_amount"] == Decimal("3000")


class TestBalanceCalculation:
    """Test balance calculation from ledger."""

    def test_basic_balance(self, calc):
        """₹50,000 total, ₹12,000 paid."""
        from unittest.mock import MagicMock

        p1 = MagicMock()
        p1.amount = Decimal("2000")
        p1.status = "COMPLETED"
        p1.is_reversal = False

        p2 = MagicMock()
        p2.amount = Decimal("2000")
        p2.status = "COMPLETED"
        p2.is_reversal = False

        p3 = MagicMock()
        p3.amount = Decimal("1000")
        p3.status = "COMPLETED"
        p3.is_reversal = False

        balance = calc.calculate_balance(
            Decimal("50000"), [p1, p2, p3]
        )
        assert balance["total_payable"] == Decimal("50000")
        assert balance["total_paid"] == Decimal("5000")
        assert balance["outstanding"] == Decimal("45000")

    def test_with_reversal(self, calc):
        """Payment and reversal."""
        from unittest.mock import MagicMock

        p1 = MagicMock()
        p1.amount = Decimal("2000")
        p1.status = "COMPLETED"
        p1.is_reversal = False

        p2 = MagicMock()
        p2.amount = Decimal("2000")
        p1.status = "COMPLETED"
        p2.is_reversal = False

        # Reversal of p1
        r1 = MagicMock()
        r1.amount = Decimal("2000")
        r1.status = "REVERSED"

        balance = calc.calculate_balance(
            Decimal("50000"), [p1, p2, r1]
        )
        assert balance["total_paid"] == Decimal("4000")
        assert balance["outstanding"] == Decimal("46000")

    def test_zero_payments(self, calc):
        """No payments yet."""
        balance = calc.calculate_balance(Decimal("50000"), [])
        assert balance["outstanding"] == Decimal("50000")
        assert balance["is_fully_paid"] is False

    def test_fully_paid(self, calc):
        """All installments paid."""
        from unittest.mock import MagicMock

        payments = []
        for i in range(10):
            p = MagicMock()
            p.amount = Decimal("5000")
            p.status = "COMPLETED"
            p.is_reversal = False
            payments.append(p)

        balance = calc.calculate_balance(Decimal("50000"), payments)
        assert balance["total_paid"] == Decimal("50000")
        assert balance["outstanding"] == Decimal("0")
        assert balance["is_fully_paid"] is True
