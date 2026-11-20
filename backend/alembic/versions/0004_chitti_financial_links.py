"""Add direct reversal and payout ledger links.

Downgrade refuses to remove columns containing financial links, because doing
so would irreversibly discard those relationships.

Revision ID: 0004_chitti_financial_links
Revises: 0003_chitti_financial_checks
Create Date: 2026-11-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import re


revision: str = "0004_chitti_financial_links"
down_revision: Union[str, None] = "0003_chitti_financial_checks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


OWNED = "owned-by-0004-chitti-financial-links"
LINK_COLUMNS = (
    ("chitti_transactions", "original_transaction_id"),
    ("chitti_payouts", "ledger_transaction_id"),
)
FOREIGN_KEYS = (
    (
        "chitti_transactions",
        "fk_chitti_transaction_original_transaction",
        ("original_transaction_id",),
        "chitti_transactions",
        ("id",),
    ),
    (
        "chitti_payouts",
        "fk_chitti_payout_ledger_transaction",
        ("ledger_transaction_id",),
        "chitti_transactions",
        ("id",),
    ),
)
UNIQUE_CONSTRAINTS = (
    (
        "chitti_transactions",
        "uq_chitti_transaction_original",
        ("original_transaction_id",),
    ),
    (
        "chitti_payouts",
        "uq_chitti_payout_ledger_transaction",
        ("ledger_transaction_id",),
    ),
)
INDEXES = (
    ("chitti_transactions", "ix_chitti_transaction_original_transaction", ("original_transaction_id",)),
    ("chitti_payouts", "ix_chitti_payout_ledger_transaction", ("ledger_transaction_id",)),
)


def _normalize_ddl(value: str) -> str:
    value = re.sub(r'"([^"]+)"', r"\1", value.lower())
    return "".join(char for char in value if char.isalnum() or char == "_")


def _column(bind, table_name: str, column_name: str):
    return next(
        (
            column
            for column in sa.inspect(bind).get_columns(table_name)
            if column["name"] == column_name
        ),
        None,
    )


def _validate_link_column(bind, table_name: str, column_name: str) -> bool:
    column = _column(bind, table_name, column_name)
    if not column:
        return False
    actual_type = column["type"].compile(dialect=bind.dialect).upper()
    if actual_type != "UUID" or column["nullable"] is not True:
        raise RuntimeError(
            f"Existing {table_name}.{column_name} must be a nullable UUID."
        )
    return True


def _foreign_key_matches(foreign_key, columns, referred_table, referred_columns) -> bool:
    return (
        tuple(foreign_key.get("constrained_columns") or ()) == columns
        and foreign_key.get("referred_table") == referred_table
        and tuple(foreign_key.get("referred_columns") or ()) == referred_columns
        and (foreign_key.get("options") or {}).get("ondelete", "").upper() == "RESTRICT"
    )


def _constraint_comment(bind, table_name: str, constraint_name: str):
    return bind.execute(
        sa.text(
            "SELECT obj_description(c.oid, 'pg_constraint') "
            "FROM pg_constraint c "
            "WHERE c.conname = :constraint_name "
            "AND c.conrelid = CAST(:table_name AS regclass)"
        ),
        {"constraint_name": constraint_name, "table_name": table_name},
    ).scalar()


def _validate_foreign_key_definition(
    bind, table_name, constraint_name, columns, referred_table, referred_columns
) -> None:
    row = bind.execute(
        sa.text(
            "SELECT contype, pg_get_constraintdef(oid), convalidated, "
            "condeferrable, condeferred FROM pg_constraint "
            "WHERE conname = :constraint_name "
            "AND conrelid = CAST(:table_name AS regclass)"
        ),
        {"constraint_name": constraint_name, "table_name": table_name},
    ).first()
    expected = (
        f"FOREIGN KEY ({', '.join(columns)}) "
        f"REFERENCES {referred_table}({', '.join(referred_columns)}) "
        "ON DELETE RESTRICT"
    )
    constraint_type = row[0].decode() if row and isinstance(row[0], bytes) else (row[0] if row else None)
    if (
        not row
        or constraint_type != "f"
        or _normalize_ddl(row[1]) != _normalize_ddl(expected)
        or not row[2]
        or row[3]
        or row[4]
    ):
        raise RuntimeError(
            f"Existing foreign key {table_name}.{constraint_name} has an incompatible definition."
        )


def _validate_unique_definition(bind, table_name, constraint_name, columns) -> None:
    row = bind.execute(
        sa.text(
            "SELECT contype, pg_get_constraintdef(oid), convalidated, "
            "condeferrable, condeferred FROM pg_constraint "
            "WHERE conname = :constraint_name "
            "AND conrelid = CAST(:table_name AS regclass)"
        ),
        {"constraint_name": constraint_name, "table_name": table_name},
    ).first()
    expected = f"UNIQUE ({', '.join(columns)})"
    constraint_type = row[0].decode() if row and isinstance(row[0], bytes) else (row[0] if row else None)
    if (
        not row
        or constraint_type != "u"
        or _normalize_ddl(row[1]) != _normalize_ddl(expected)
        or not row[2]
        or row[3]
        or row[4]
    ):
        raise RuntimeError(
            f"Existing unique constraint {table_name}.{constraint_name} has an incompatible definition."
        )


def _index_state(bind, index_name: str):
    return bind.execute(
        sa.text(
            "SELECT i.indisvalid, i.indisready, i.indisunique, "
            "i.indnkeyatts, i.indnatts, am.amname, "
            "pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_am am ON am.oid = c.relam "
            "WHERE c.relname = :index_name AND n.nspname = current_schema()"
        ),
        {"index_name": index_name},
    ).first()


def _ensure_foreign_key(
    bind,
    table_name,
    constraint_name,
    columns,
    referred_table,
    referred_columns,
) -> None:
    foreign_keys = sa.inspect(bind).get_foreign_keys(table_name)
    named = next((fk for fk in foreign_keys if fk.get("name") == constraint_name), None)
    if named:
        if not _foreign_key_matches(named, columns, referred_table, referred_columns):
            raise RuntimeError(
                f"Existing foreign key {table_name}.{constraint_name} is incompatible."
            )
        _validate_foreign_key_definition(
            bind, table_name, constraint_name, columns, referred_table, referred_columns
        )
        return

    related = [
        fk for fk in foreign_keys
        if set(fk.get("constrained_columns") or ()) & set(columns)
    ]
    if any(not _foreign_key_matches(fk, columns, referred_table, referred_columns) for fk in related):
        raise RuntimeError(
            f"Existing foreign key on {table_name}.{columns[0]} is incompatible."
        )
    if related:
        for foreign_key in related:
            _validate_foreign_key_definition(
                bind,
                table_name,
                foreign_key["name"],
                columns,
                referred_table,
                referred_columns,
            )
        return

    op.create_foreign_key(
        constraint_name,
        table_name,
        referred_table,
        list(columns),
        list(referred_columns),
        ondelete="RESTRICT",
    )
    op.execute(
        f"COMMENT ON CONSTRAINT {constraint_name} ON {table_name} IS '{OWNED}'"
    )


def _ensure_unique_constraint(bind, table_name, constraint_name, columns) -> None:
    constraints = sa.inspect(bind).get_unique_constraints(table_name)
    named = next((item for item in constraints if item.get("name") == constraint_name), None)
    if named:
        if tuple(named.get("column_names") or ()) != columns:
            raise RuntimeError(
                f"Existing unique constraint {table_name}.{constraint_name} is incompatible."
            )
        _validate_unique_definition(bind, table_name, constraint_name, columns)
        return
    equivalent = next(
        (item for item in constraints if tuple(item.get("column_names") or ()) == columns),
        None,
    )
    if equivalent:
        _validate_unique_definition(bind, table_name, equivalent["name"], columns)
        return

    op.create_unique_constraint(constraint_name, table_name, list(columns))
    op.execute(
        f"COMMENT ON CONSTRAINT {constraint_name} ON {table_name} IS '{OWNED}'"
    )


def _ensure_index(bind, table_name, index_name, columns) -> None:
    indexes = sa.inspect(bind).get_indexes(table_name)
    named = next((item for item in indexes if item.get("name") == index_name), None)
    if named:
        options = named.get("dialect_options") or {}
        if (
            tuple(named.get("column_names") or ()) != columns
            or bool(named.get("unique"))
            or options.get("postgresql_where") is not None
        ):
            raise RuntimeError(f"Existing index {table_name}.{index_name} is incompatible.")
        state = _index_state(bind, index_name)
        if (
            not state
            or state[0] is not True
            or state[1] is not True
            or state[2] is not False
            or state[3] != 1
            or state[4] != 1
            or state[5] != "btree"
            or state[6] is not None
        ):
            raise RuntimeError(f"Existing index {table_name}.{index_name} is not valid.")
        return

    op.create_index(index_name, table_name, list(columns), unique=False)
    op.execute(f"COMMENT ON INDEX {index_name} IS '{OWNED}'")


def _drop_owned_constraint(table_name: str, constraint_name: str, constraint_type: str) -> None:
    bind = op.get_bind()
    if _constraint_comment(bind, table_name, constraint_name) == OWNED:
        op.drop_constraint(constraint_name, table_name, type_=constraint_type)


def _index_comment(bind, index_name: str):
    return bind.execute(
        sa.text(
            "SELECT obj_description(c.oid, 'pg_class') "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind = 'i' AND n.nspname = current_schema() "
            "AND c.relname = :index_name"
        ),
        {"index_name": index_name},
    ).scalar()


def upgrade() -> None:
    bind = op.get_bind()
    for table_name, column_name in LINK_COLUMNS:
        if not _validate_link_column(bind, table_name, column_name):
            op.add_column(
                table_name,
                sa.Column(column_name, sa.UUID(), nullable=True),
            )
            op.execute(
                f"COMMENT ON COLUMN {table_name}.{column_name} IS '{OWNED}'"
            )

    for definition in FOREIGN_KEYS:
        _ensure_foreign_key(bind, *definition)
    for definition in UNIQUE_CONSTRAINTS:
        _ensure_unique_constraint(bind, *definition)
    for definition in INDEXES:
        _ensure_index(bind, *definition)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name, column_name in LINK_COLUMNS:
        if not _validate_link_column(bind, table_name, column_name):
            continue
        if bind.execute(
            sa.text(
                f"SELECT 1 FROM {table_name} "
                f"WHERE {column_name} IS NOT NULL LIMIT 1"
            )
        ).first():
            raise RuntimeError(
                "Refusing to downgrade 0004: financial link values exist; "
                "export or preserve them before removing this revision."
            )

    for table_name, index_name, _ in reversed(INDEXES):
        if _index_comment(bind, index_name) == OWNED:
            op.drop_index(index_name, table_name=table_name)

    for table_name, constraint_name, _ in reversed(UNIQUE_CONSTRAINTS):
        _drop_owned_constraint(table_name, constraint_name, "unique")
    for table_name, constraint_name, *_ in reversed(FOREIGN_KEYS):
        _drop_owned_constraint(table_name, constraint_name, "foreignkey")

    for table_name, column_name in reversed(LINK_COLUMNS):
        column = _column(bind, table_name, column_name)
        if column and column.get("comment") == OWNED:
            op.drop_column(table_name, column_name)
