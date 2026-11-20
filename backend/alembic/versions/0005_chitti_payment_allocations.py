"""Add contribution payment allocation and member credit movements.

Revision ID: 0005_chitti_payment_allocations
Revises: 0004_chitti_financial_links
Create Date: 2026-11-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_chitti_payment_allocations"
down_revision: Union[str, None] = "0004_chitti_financial_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "chitti_payment_allocations"
OWNED = "owned-by-0005-chitti-payment-allocations"
EXPECTED_COLUMNS = {
    "id": ("uuid", False),
    "chitti_id": ("uuid", False),
    "member_id": ("uuid", False),
    "source_transaction_id": ("uuid", False),
    "event_transaction_id": ("uuid", True),
    "contribution_id": ("uuid", True),
    "allocation_type": ("chitti_payment_allocation_type_enum", False),
    "event_type": ("chitti_payment_allocation_event_type_enum", False),
    "amount": ("numeric(12, 2)", False),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}
CHECKS = {
    "ck_chitti_payment_allocation_amount_nonzero": "CHECK (amount <> 0)",
    "ck_chitti_payment_allocation_target": (
        "CHECK (((allocation_type = 'CREDIT' AND contribution_id IS NULL) OR "
        "(allocation_type = 'CONTRIBUTION' AND contribution_id IS NOT NULL)))"
    ),
}
FOREIGN_KEYS = {
    "fk_chitti_payment_allocations_chitti_id": (
        ("chitti_id",), "chittis", ("id",), "CASCADE"
    ),
    "fk_chitti_payment_allocations_member_id": (
        ("member_id",), "chitti_members", ("id",), "RESTRICT"
    ),
    "fk_chitti_payment_allocations_source_transaction_id": (
        ("source_transaction_id",), "chitti_transactions", ("id",), "RESTRICT"
    ),
    "fk_chitti_payment_allocations_event_transaction_id": (
        ("event_transaction_id",), "chitti_transactions", ("id",), "RESTRICT"
    ),
    "fk_chitti_payment_allocations_contribution_id": (
        ("contribution_id",), "chitti_member_contributions", ("id",), "RESTRICT"
    ),
}
INDEXES = {
    "ix_chitti_payment_allocations_id": ("id",),
    "ix_chitti_payment_allocations_source_transaction": ("source_transaction_id",),
    "ix_chitti_payment_allocations_member": ("chitti_id", "member_id"),
    "ix_chitti_payment_allocations_contribution": ("contribution_id",),
}


def _normalize(value):
    import re

    value = re.sub(r"\bcheck\b", "", value.lower())
    value = re.sub(r"::\s*[a-z0-9_]+", "", value)
    value = value.replace('"', "")
    value = re.sub(r"\(([a-z_][a-z0-9_]*)\)", r"\1", value)
    # PostgreSQL represents numeric literals in constraints as `(0)::numeric`.
    # After removing the type cast, normalize the harmless remaining parens.
    value = re.sub(r"\((\d+(?:\.\d+)?)\)", r"\1", value)
    # The two allocation checks contain only comparisons joined by AND/OR;
    # PostgreSQL may add redundant grouping parentheses around each comparison.
    value = value.replace("(", "").replace(")", "")
    tokens = re.findall(
        r"'(?:''|[^'])*'|[a-z_][a-z0-9_]*|\d+(?:\.\d+)?|<>|!=|>=|<=|[=()]",
        value,
    )
    position = 0

    def parse_atom():
        nonlocal position
        if tokens[position] == "(":
            position += 1
            result = parse_or()
            if tokens[position] != ")":
                raise ValueError(f"Unbalanced CHECK expression: {value}")
            position += 1
            return result
        left = tokens[position]
        position += 1
        if tokens[position] == "is":
            position += 1
            negated = tokens[position] == "not"
            if negated:
                position += 1
            if tokens[position] != "null":
                raise ValueError(f"Invalid NULL CHECK expression: {value}")
            position += 1
            return ("IS NOT NULL" if negated else "IS NULL", left)
        operator = tokens[position]
        position += 1
        right = tokens[position]
        position += 1
        return (operator, left, right)

    def parse_and():
        nonlocal position
        result = parse_atom()
        while position < len(tokens) and tokens[position] == "and":
            position += 1
            result = ("AND", result, parse_atom())
        return result

    def parse_or():
        nonlocal position
        result = parse_and()
        while position < len(tokens) and tokens[position] == "or":
            position += 1
            result = ("OR", result, parse_and())
        return result

    parsed = parse_or()
    if position != len(tokens):
        raise ValueError(f"Unexpected CHECK expression tokens: {value}")
    return parsed


def _validate_existing(bind):
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns(TABLE)}
    for name, (expected_type, expected_nullable) in EXPECTED_COLUMNS.items():
        column = columns.get(name)
        if not column:
            raise RuntimeError(f"Existing {TABLE} is missing required column {name}.")
        actual_type = column["type"].compile(dialect=bind.dialect).lower()
        if (
            actual_type != expected_type
            or column["nullable"] is not expected_nullable
        ):
            raise RuntimeError(f"Existing {TABLE}.{name} has an incompatible definition.")
    if inspector.get_pk_constraint(TABLE).get("constrained_columns") != ["id"]:
        raise RuntimeError(f"Existing {TABLE} has an incompatible primary key.")

    named_checks = {
        row[0]: row
        for row in bind.execute(
            sa.text(
                "SELECT conname, contype, pg_get_constraintdef(oid), convalidated "
                "FROM pg_constraint WHERE conrelid = CAST(:table_name AS regclass)"
            ),
            {"table_name": TABLE},
        ).all()
    }
    for name, definition in CHECKS.items():
        row = named_checks.get(name)
        constraint_type = row[1].decode() if row and isinstance(row[1], bytes) else (row[1] if row else None)
        if (
            not row
            or constraint_type != "c"
            or not row[3]
            or _normalize(row[2]) != _normalize(definition)
        ):
            raise RuntimeError(f"Existing {TABLE}.{name} has an incompatible definition.")

    foreign_keys = {
        item.get("name"): item for item in inspector.get_foreign_keys(TABLE)
    }
    for name, (columns, referred_table, referred_columns, ondelete) in FOREIGN_KEYS.items():
        item = foreign_keys.get(name)
        if (
            not item
            or tuple(item.get("constrained_columns") or ()) != columns
            or item.get("referred_table") != referred_table
            or tuple(item.get("referred_columns") or ()) != referred_columns
            or (item.get("options") or {}).get("ondelete", "").upper() != ondelete
        ):
            raise RuntimeError(f"Existing {TABLE}.{name} has an incompatible definition.")

    actual_indexes = {item["name"]: item for item in inspector.get_indexes(TABLE)}
    for name, expected_columns in INDEXES.items():
        item = actual_indexes.get(name)
        if (
            not item
            or tuple(item.get("column_names") or ()) != expected_columns
            or item.get("unique")
        ):
            raise RuntimeError(f"Existing index {name} has an incompatible definition.")

    enum_labels = bind.execute(
        sa.text(
            "SELECT t.typname, e.enumlabel FROM pg_type t "
            "JOIN pg_enum e ON e.enumtypid = t.oid "
            "WHERE t.typname IN "
            "('chitti_payment_allocation_type_enum', "
            "'chitti_payment_allocation_event_type_enum') "
            "ORDER BY t.typname, e.enumsortorder"
        )
    ).all()
    enums = {}
    for enum_name, label in enum_labels:
        enums.setdefault(enum_name, []).append(label)
    if enums.get("chitti_payment_allocation_type_enum") != ["CONTRIBUTION", "CREDIT"]:
        raise RuntimeError(f"Existing {TABLE} allocation_type enum is incompatible.")
    if enums.get("chitti_payment_allocation_event_type_enum") != [
        "PAYMENT", "REVERSAL", "CREDIT_UTILIZATION", "LIFT_ADJUSTMENT"
    ]:
        raise RuntimeError(f"Existing {TABLE} event_type enum is incompatible.")


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE):
        _validate_existing(bind)
        return

    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chitti_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contribution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "allocation_type",
            sa.Enum("CONTRIBUTION", "CREDIT", name="chitti_payment_allocation_type_enum"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.Enum(
                "PAYMENT", "REVERSAL", "CREDIT_UTILIZATION", "LIFT_ADJUSTMENT",
                name="chitti_payment_allocation_event_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount <> 0", name="ck_chitti_payment_allocation_amount_nonzero"),
        sa.CheckConstraint(
            "(allocation_type = 'CREDIT' AND contribution_id IS NULL) OR "
            "(allocation_type = 'CONTRIBUTION' AND contribution_id IS NOT NULL)",
            name="ck_chitti_payment_allocation_target",
        ),
        sa.ForeignKeyConstraint(
            ["chitti_id"], ["chittis.id"],
            name="fk_chitti_payment_allocations_chitti_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["chitti_members.id"],
            name="fk_chitti_payment_allocations_member_id", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_transaction_id"], ["chitti_transactions.id"],
            name="fk_chitti_payment_allocations_source_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_transaction_id"], ["chitti_transactions.id"],
            name="fk_chitti_payment_allocations_event_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contribution_id"], ["chitti_member_contributions.id"],
            name="fk_chitti_payment_allocations_contribution_id", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(f"COMMENT ON TABLE {TABLE} IS '{OWNED}'")
    for name, columns in INDEXES.items():
        op.create_index(name, TABLE, list(columns), unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    comment = bind.execute(
        sa.text(
            "SELECT obj_description(to_regclass(:table_name), 'pg_class')"
        ),
        {"table_name": TABLE},
    ).scalar()
    if comment != OWNED:
        return
    if bind.execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError(
            "Refusing to downgrade 0005: payment allocation history exists."
        )
    for name in reversed(tuple(INDEXES)):
        op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
    postgresql.ENUM(
        "CONTRIBUTION",
        "CREDIT",
        name="chitti_payment_allocation_type_enum",
    ).drop(bind, checkfirst=True)
    postgresql.ENUM(
        "PAYMENT",
        "REVERSAL",
        "CREDIT_UTILIZATION",
        "LIFT_ADJUSTMENT",
        name="chitti_payment_allocation_event_type_enum",
    ).drop(bind, checkfirst=True)
