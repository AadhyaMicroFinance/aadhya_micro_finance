"""Add named non-negative Chitti financial CHECK constraints.

Revision ID: 0003_chitti_financial_checks
Revises: 0002_lift_events
Create Date: 2026-11-19
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text
import re


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


def _normalize_check(definition: str):
    value = re.sub(r"\bcheck\b", "", definition.lower())
    value = re.sub(r"::\s*(numeric|integer|bigint|smallint|real|double precision)", "", value)
    value = value.replace('"', "")
    compact = re.sub(r"\s+", "", value)
    tokens = re.findall(
        r"[a-z_][a-z0-9_]*|\d+(?:\.\d+)?|>=|<=|<>|!=|[=()+\-*/]",
        compact,
    )
    if "".join(tokens) != compact:
        raise ValueError(f"Unsupported CHECK expression: {definition}")

    position = 0

    def parse_atom():
        nonlocal position
        token = tokens[position]
        if token == "(":
            position += 1
            result = parse_comparison()
            if tokens[position] != ")":
                raise ValueError(f"Unbalanced CHECK expression: {definition}")
            position += 1
            return result
        if token in (")", "=", ">=", "<=", "<>", "!=", "+", "-", "*", "/"):
            raise ValueError(f"Invalid CHECK expression: {definition}")
        position += 1
        return token

    def parse_product():
        nonlocal position
        result = parse_atom()
        while position < len(tokens) and tokens[position] in ("*", "/"):
            operator = tokens[position]
            position += 1
            result = (operator, result, parse_atom())
        return result

    def parse_sum():
        nonlocal position
        result = parse_product()
        while position < len(tokens) and tokens[position] in ("+", "-"):
            operator = tokens[position]
            position += 1
            result = (operator, result, parse_product())
        return result

    def parse_comparison():
        nonlocal position
        result = parse_sum()
        if position < len(tokens) and tokens[position] in ("=", ">=", "<=", "<>", "!="):
            operator = tokens[position]
            position += 1
            result = (operator, result, parse_sum())
        return result

    parsed = parse_comparison()
    if position != len(tokens):
        raise ValueError(f"Unexpected CHECK expression tokens: {definition}")
    return parsed


def _constraint_definition(bind, table_name: str, constraint_name: str):
    return bind.execute(
        text(
            "SELECT contype, pg_get_constraintdef(oid), convalidated, "
            "obj_description(oid, 'pg_constraint') "
            "FROM pg_constraint "
            "WHERE conname = :constraint_name "
            "AND conrelid = CAST(:table_name AS regclass)"
        ),
        {
            "constraint_name": constraint_name,
            "table_name": table_name,
        },
    ).first()


def _validate_constraint(row, table_name: str, constraint_name: str, condition: str) -> None:
    constraint_type = row[0].decode() if row and isinstance(row[0], bytes) else (row[0] if row else None)
    if not row or constraint_type != "c" or not row[2]:
        raise RuntimeError(
            f"Constraint {table_name}.{constraint_name} is not a validated CHECK constraint."
        )
    if _normalize_check(row[1]) != _normalize_check(f"CHECK ({condition})"):
        raise RuntimeError(
            f"Constraint {table_name}.{constraint_name} has an incompatible definition."
        )


def upgrade() -> None:
    bind = op.get_bind()
    for table_name, constraint_name, condition in CONSTRAINTS:
        existing = _constraint_definition(bind, table_name, constraint_name)
        if existing:
            _validate_constraint(existing, table_name, constraint_name, condition)
            continue
        op.create_check_constraint(
            constraint_name,
            table_name,
            condition,
        )
        op.execute(
            f"COMMENT ON CONSTRAINT {constraint_name} ON {table_name} "
            "IS 'owned-by-0003-chitti-financial-checks'"
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name, constraint_name, condition in reversed(CONSTRAINTS):
        existing = _constraint_definition(bind, table_name, constraint_name)
        if not existing:
            continue
        _validate_constraint(existing, table_name, constraint_name, condition)
        if existing[3] == "owned-by-0003-chitti-financial-checks":
            op.drop_constraint(
                constraint_name,
                table_name,
                type_="check",
            )
