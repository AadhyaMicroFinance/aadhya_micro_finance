"""Add named non-negative Chitti financial CHECK constraints.

Revision ID: 0003_chitti_financial_checks
Revises: 0002_lift_events
Create Date: 2026-11-19
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "0003_chitti_financial_checks"
down_revision: Union[str, None] = "0002_lift_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINTS = (
    ("chitti_member_contributions", "ck_chitti_contribution_expected_amount_nonnegative", "expected_amount >= 0"),
    ("chitti_member_contributions", "ck_chitti_contribution_paid_amount_nonnegative", "paid_amount >= 0"),
    ("chitti_member_contributions", "ck_chitti_contribution_remaining_amount_nonnegative", "remaining_amount >= 0"),
    ("chitti_period_schedule", "ck_chitti_period_expected_collection_nonnegative", "expected_collection >= 0"),
    ("chitti_period_schedule", "ck_chitti_period_actual_collection_nonnegative", "actual_collection >= 0"),
    ("chitti_period_schedule", "ck_chitti_period_pending_collection_nonnegative", "pending_collection >= 0"),
    ("chitti_period_schedule", "ck_chitti_period_expected_payout_nonnegative", "expected_payout >= 0"),
    ("chitti_period_schedule", "ck_chitti_period_actual_payout_nonnegative", "actual_payout >= 0"),
    ("chitti_payouts", "ck_chitti_payout_gross_nonnegative", "gross_payout >= 0"),
    ("chitti_payouts", "ck_chitti_payout_discount_nonnegative", "discount_amount >= 0"),
    ("chitti_payouts", "ck_chitti_payout_fee_nonnegative", "fee_amount >= 0"),
    ("chitti_payouts", "ck_chitti_payout_net_nonnegative", "net_payout >= 0"),
    (
        "chitti_payouts",
        "ck_chitti_payout_net_arithmetic",
        "net_payout = gross_payout - discount_amount - fee_amount",
    ),
    ("chitti_transactions", "ck_chitti_transaction_amount_nonnegative", "amount >= 0"),
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name, constraint_name, condition in CONSTRAINTS:
        exists = bind.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = :constraint_name "
                "AND conrelid = CAST(:table_name AS regclass)"
            ),
            {
                "constraint_name": constraint_name,
                "table_name": table_name,
            },
        ).first()
        if exists:
            continue
        op.create_check_constraint(
            constraint_name,
            table_name,
            condition,
        )


def downgrade() -> None:
    for table_name, constraint_name, _ in reversed(CONSTRAINTS):
        op.drop_constraint(
            constraint_name,
            table_name,
            type_="check",
        )
