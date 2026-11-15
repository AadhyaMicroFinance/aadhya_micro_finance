"""Regression coverage for the approved lift-based 1% surcharge."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.chitti_calculation import ChittiCalculationEngine


@pytest.mark.parametrize(
    ("members", "periods", "installment", "expected"),
    [(2, 14, 100, 2800), (3, 14, 100, 4200), (5, 14, 100, 7000),
     (3, 14, 200, 8400), (3, 30, 100, 9000)],
)
def test_fixed_chitti_total_formula(members, periods, installment, expected) -> None:
    engine = ChittiCalculationEngine({
        "total_value": 1, "member_count": members, "duration": periods,
        "frequency": "DAILY",
        "contribution_rules": {"type": "FIXED", "installment_amount": installment},
        "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
    })
    assert engine.calculate_fixed_total_value(members) == Decimal(expected)


@pytest.mark.parametrize(
    ("frequency", "days_per_period"),
    [("DAILY", 1), ("WEEKLY", 7), ("MONTHLY", 30)],
)
def test_lift_surcharge_starts_next_period_and_uses_original_value(
    frequency: str, days_per_period: int
) -> None:
    engine = ChittiCalculationEngine(
        {
            "total_value": 120000,
            "member_count": 10,
            "duration": 8,
            "frequency": frequency,
            "contribution_rules": {"type": "LIFT_BASED", "regular_amount": 5000},
            "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
        }
    )

    contributions = engine.generate_member_contributions(
        "member-5", 5, date(2026, 1, 1), member_lift_period=5
    )
    assert [entry["expected_amount"] for entry in contributions] == [
        Decimal("5000"),
        Decimal("5000"),
        Decimal("5000"),
        Decimal("5000"),
        Decimal("5000"),  # lift period: no surcharge yet
        Decimal("6200"),
        Decimal("6200"),
        Decimal("6200"),  # original final period; no extension
    ]
    schedule = engine.generate_period_schedule(date(2026, 1, 1), 10)
    assert schedule[1]["due_date"] == date(2026, 1, 1) + timedelta(days=days_per_period)
    assert schedule[0]["expected_collection"] == Decimal("50000")
    # Generic period projection has no member lift events; member-specific
    # expected rows above verify the surcharge formula and API projections
    # aggregate those rows once an event exists.
    assert schedule[1]["expected_collection"] == Decimal("50000")
    assert len(schedule) == 8


def test_legacy_lift_rule_uses_explicit_lift_and_keeps_saved_pre_post_amounts() -> None:
    engine = ChittiCalculationEngine(
        {
            "total_value": 120000,
            "member_count": 2,
            "duration": 3,
            "frequency": "WEEKLY",
            "contribution_rules": {
                "type": "LIFT_BASED",
                "pre_lift_amount": 1000,
                "post_lift_amount": 1500,
            },
            "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
        }
    )
    member = engine.generate_member_contributions("member-1", 1, date(2026, 1, 1))
    assert [entry["expected_amount"] for entry in member] == [
        Decimal("1000"), Decimal("1000"), Decimal("1000"),
    ]
    lifted = engine.generate_member_contributions(
        "member-1", 1, date(2026, 1, 1), member_lift_period=1
    )
    assert [entry["expected_amount"] for entry in lifted] == [
        Decimal("1000"), Decimal("2200"), Decimal("2200"),
    ]


def test_payout_order_does_not_implicitly_create_a_lift() -> None:
    engine = ChittiCalculationEngine(
        {
            "total_value": 120000,
            "member_count": 3,
            "duration": 6,
            "frequency": "MONTHLY",
            "contribution_rules": {"type": "LIFT_BASED", "regular_amount": 5000},
            "payout_rules": {
                "type": "CUSTOM",
                "payout_schedule": [
                    {"period": 1, "member_number": 1},
                    {"period": 5, "member_number": 2},
                    {"period": 6, "member_number": 3},
                    {"period": 2, "member_number": 1},
                    {"period": 3, "member_number": 1},
                    {"period": 4, "member_number": 1},
                ],
            },
        }
    )
    member = engine.generate_member_contributions("member-2", 2, date(2026, 1, 1))
    assert [row["expected_amount"] for row in member] == [
        Decimal("5000"), Decimal("5000"), Decimal("5000"),
        Decimal("5000"), Decimal("5000"), Decimal("5000"),
    ]

    lifted = engine.generate_member_contributions(
        "member-2", 2, date(2026, 1, 1), member_lift_period=5
    )
    assert [row["expected_amount"] for row in lifted] == [
        Decimal("5000"), Decimal("5000"), Decimal("5000"),
        Decimal("5000"), Decimal("5000"), Decimal("6200"),
    ]


def test_lift_in_final_period_has_no_surcharge() -> None:
    engine = ChittiCalculationEngine({
        "total_value": 120000, "member_count": 1, "duration": 3,
        "frequency": "MONTHLY",
        "contribution_rules": {"type": "LIFT_BASED", "regular_amount": 1000},
        "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
    })
    rows = engine.generate_member_contributions(
        "member", 1, date(2026, 1, 1), member_lift_period=3
    )
    assert [row["expected_amount"] for row in rows] == [Decimal("1000")] * 3