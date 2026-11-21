"""Operator-driven credit application, over-allocation resolution and refunds.

Adds the enum labels, the allocation-target CHECK branch for unresolved excess
and the refund linkage CHECK. No columns, no data changes and no backfill.

Revision ID: 0007_chitti_credit_resolution
Revises: 0006_multi_slot_membership
Create Date: 2026-11-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_chitti_credit_resolution"
down_revision: Union[str, None] = "0006_multi_slot_membership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OWNED = "owned-by-0007-chitti-credit-resolution"
ALLOCATION_TABLE = "chitti_payment_allocations"
TRANSACTION_TABLE = "chitti_transactions"

# Revision 0001 builds the enums from the model metadata, which keeps the
# historical labels, so every database reaches this revision with exactly the
# labels defined by 0005. Each entry must therefore be missing here; the
# ``IF NOT EXISTS`` form only makes a resumed partial upgrade safe.
ENUM_ADDITIONS = (
    ("chitti_payment_allocation_type_enum", "UNRESOLVED"),
    ("chitti_payment_allocation_event_type_enum", "EXCESS_RESOLUTION"),
    ("chitti_transaction_type_enum", "CREDIT_UTILIZATION"),
    ("chitti_transaction_type_enum", "EXCESS_RESOLUTION"),
    ("chitti_transaction_type_enum", "REFUND"),
)

TARGET_CHECK = "ck_chitti_payment_allocation_target"
TARGET_LEGACY = (
    "(allocation_type = 'CREDIT' AND contribution_id IS NULL) OR "
    "(allocation_type = 'CONTRIBUTION' AND contribution_id IS NOT NULL)"
)
TARGET_CURRENT = (
    "(allocation_type = 'CREDIT' AND contribution_id IS NULL) OR "
    "(allocation_type = 'CONTRIBUTION' AND contribution_id IS NOT NULL) OR "
    "(allocation_type = 'UNRESOLVED' AND contribution_id IS NULL)"
)

REFUND_CHECK = "ck_chitti_transaction_refund_unlinked"
REFUND_CONDITION = (
    "transaction_type <> 'REFUND' OR original_transaction_id IS NULL"
)

CUSTOMER_INDEX = "ix_chitti_members_customer_id"

# Only values that cannot exist before this revision. Legacy credit rows
# (allocation_type='CREDIT', event_type='CREDIT_UTILIZATION' with a NULL event
# transaction, LIFT_ADJUSTMENT pairs) must never block a downgrade.
NEW_ALLOCATION_TYPES = ("UNRESOLVED",)
NEW_ALLOCATION_EVENTS = ("EXCESS_RESOLUTION",)
NEW_TRANSACTION_TYPES = ("CREDIT_UTILIZATION", "EXCESS_RESOLUTION", "REFUND")


def _normalize(definition: str) -> str:
    import re

    value = definition.lower()
    value = value.replace("check", "")
    value = re.sub(r"::\s*[a-z0-9_]+", "", value)
    value = re.sub(r"[\s\"()]", "", value)
    return value


def _constraint_definition(bind, table_name: str, constraint_name: str):
    return bind.execute(
        sa.text(
            "SELECT contype, pg_get_constraintdef(oid), convalidated, "
            "obj_description(oid, 'pg_constraint') "
            "FROM pg_constraint "
            "WHERE conname = :constraint_name "
            "AND conrelid = CAST(:table_name AS regclass)"
        ),
        {"constraint_name": constraint_name, "table_name": table_name},
    ).first()


def _enum_labels(bind, enum_name: str):
    rows = bind.execute(
        sa.text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = :enum_name "
            "ORDER BY e.enumsortorder"
        ),
        {"enum_name": enum_name},
    ).all()
    return [row[0] for row in rows]


def _ensure_enum_labels(bind) -> None:
    for enum_name, label in ENUM_ADDITIONS:
        labels = _enum_labels(bind, enum_name)
        if not labels:
            raise RuntimeError(
                f"Enum type {enum_name} does not exist; schema is not at 0005."
            )
        if label in labels:
            continue
        # ALTER TYPE ... ADD VALUE cannot share a transaction with later use of
        # the new label, so it is committed before the CHECK constraints below.
        with op.get_context().autocommit_block():
            op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{label}'")


def _ensure_target_check(bind) -> None:
    row = _constraint_definition(bind, ALLOCATION_TABLE, TARGET_CHECK)
    if not row:
        op.create_check_constraint(TARGET_CHECK, ALLOCATION_TABLE, TARGET_CURRENT)
        op.execute(
            f"COMMENT ON CONSTRAINT {TARGET_CHECK} ON {ALLOCATION_TABLE} "
            f"IS '{OWNED}'"
        )
        return
    constraint_type = (
        row[0].decode() if isinstance(row[0], bytes) else row[0]
    )
    if constraint_type != "c" or not row[2]:
        raise RuntimeError(
            f"Existing {ALLOCATION_TABLE}.{TARGET_CHECK} is not a validated "
            "CHECK constraint."
        )
    definition = _normalize(row[1])
    if definition == _normalize(TARGET_CURRENT):
        return
    if definition != _normalize(TARGET_LEGACY):
        raise RuntimeError(
            f"Existing {ALLOCATION_TABLE}.{TARGET_CHECK} has an unrecognised "
            "definition."
        )
    op.drop_constraint(TARGET_CHECK, ALLOCATION_TABLE, type_="check")
    op.create_check_constraint(TARGET_CHECK, ALLOCATION_TABLE, TARGET_CURRENT)
    op.execute(
        f"COMMENT ON CONSTRAINT {TARGET_CHECK} ON {ALLOCATION_TABLE} IS '{OWNED}'"
    )


def _ensure_refund_check(bind) -> None:
    row = _constraint_definition(bind, TRANSACTION_TABLE, REFUND_CHECK)
    if not row:
        op.create_check_constraint(
            REFUND_CHECK, TRANSACTION_TABLE, REFUND_CONDITION
        )
        op.execute(
            f"COMMENT ON CONSTRAINT {REFUND_CHECK} ON {TRANSACTION_TABLE} "
            f"IS '{OWNED}'"
        )
        return
    constraint_type = (
        row[0].decode() if isinstance(row[0], bytes) else row[0]
    )
    if (
        constraint_type != "c"
        or not row[2]
        or _normalize(row[1]) != _normalize(REFUND_CONDITION)
    ):
        raise RuntimeError(
            f"Existing {TRANSACTION_TABLE}.{REFUND_CHECK} has an incompatible "
            "definition."
        )


def _ensure_customer_index(bind) -> None:
    indexes = sa.inspect(bind).get_indexes("chitti_members")
    existing = next(
        (item for item in indexes if item.get("name") == CUSTOMER_INDEX), None
    )
    if existing:
        if tuple(existing.get("column_names") or ()) != ("customer_id",):
            raise RuntimeError(
                f"Existing index {CUSTOMER_INDEX} covers unexpected columns."
            )
        return
    op.create_index(CUSTOMER_INDEX, "chitti_members", ["customer_id"], unique=False)
    op.execute(f"COMMENT ON INDEX {CUSTOMER_INDEX} IS '{OWNED}'")


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(ALLOCATION_TABLE):
        raise RuntimeError(
            f"{ALLOCATION_TABLE} does not exist; apply revision 0005 first."
        )
    _ensure_enum_labels(bind)
    _ensure_target_check(bind)
    _ensure_refund_check(bind)
    _ensure_customer_index(bind)


def _refuse_downgrade(bind, query: str, reason: str) -> None:
    if bind.execute(sa.text(query)).first():
        raise RuntimeError(f"Refusing to downgrade 0007: {reason}")


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(ALLOCATION_TABLE):
        return

    _refuse_downgrade(
        bind,
        f"SELECT 1 FROM {ALLOCATION_TABLE} "
        f"WHERE allocation_type IN "
        f"({', '.join(repr(value) for value in NEW_ALLOCATION_TYPES)}) LIMIT 1",
        "payments carry unresolved excess that only this revision can represent.",
    )
    _refuse_downgrade(
        bind,
        f"SELECT 1 FROM {ALLOCATION_TABLE} "
        f"WHERE event_type IN "
        f"({', '.join(repr(value) for value in NEW_ALLOCATION_EVENTS)}) LIMIT 1",
        "excess resolutions exist that only this revision can represent.",
    )
    _refuse_downgrade(
        bind,
        f"SELECT 1 FROM {TRANSACTION_TABLE} "
        f"WHERE transaction_type IN "
        f"({', '.join(repr(value) for value in NEW_TRANSACTION_TYPES)}) LIMIT 1",
        "credit utilizations, excess resolutions or refunds exist.",
    )

    row = _constraint_definition(bind, ALLOCATION_TABLE, TARGET_CHECK)
    if row and _normalize(row[1]) == _normalize(TARGET_CURRENT):
        op.drop_constraint(TARGET_CHECK, ALLOCATION_TABLE, type_="check")
        op.create_check_constraint(
            TARGET_CHECK, ALLOCATION_TABLE, TARGET_LEGACY
        )

    row = _constraint_definition(bind, TRANSACTION_TABLE, REFUND_CHECK)
    if row:
        comment = row[3]
        if comment == OWNED:
            op.drop_constraint(REFUND_CHECK, TRANSACTION_TABLE, type_="check")

    indexes = sa.inspect(bind).get_indexes("chitti_members")
    existing = next(
        (item for item in indexes if item.get("name") == CUSTOMER_INDEX), None
    )
    if existing:
        op.drop_index(CUSTOMER_INDEX, table_name="chitti_members")

    # Enum labels are intentionally kept: PostgreSQL cannot remove a value, and
    # 0005's downgrade drops the allocation enums only when no history exists.
