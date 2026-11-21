"""Multi-slot integrity: per-slot lift, case-insensitive alias, one agreement per slot.

Revision ID: 0008_multi_slot_integrity
Revises: 0007_chitti_credit_resolution

This revision only replaces indexes and adds a uniqueness constraint. It does
not read, rewrite or delete any business row, so historical lift events,
aliases and agreements keep their original values.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_multi_slot_integrity"
down_revision: Union[str, None] = "0007_chitti_credit_resolution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LIFT_TABLE = "chitti_lift_events"
LIFT_INDEX = "uq_chitti_lift_period_active"
LIFT_OLD_COLUMNS = ("chitti_id", "period_number")
LIFT_NEW_COLUMNS = ("chitti_id", "member_id", "period_number")
LIFT_PREDICATE = "reversed_at IS NULL"

MEMBER_TABLE = "chitti_members"
ALIAS_INDEX = "uq_chitti_member_alias"
ALIAS_CI_INDEX = "uq_chitti_member_alias_ci"
ALIAS_PREDICATE = "alias IS NOT NULL"

AGREEMENT_TABLE = "chitti_agreements"
AGREEMENT_CONSTRAINT = "uq_chitti_agreement_member"


def _index_columns(bind, table_name: str, index_name: str):
    index = next(
        (
            row for row in sa.inspect(bind).get_indexes(table_name)
            if row.get("name") == index_name
        ),
        None,
    )
    if not index:
        return None
    return tuple(index.get("column_names") or ())


def _has_constraint(bind, table_name: str, constraint_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = :name AND conrelid = CAST(:table AS regclass)"
            ),
            {"name": constraint_name, "table": table_name},
        ).first()
    )


def _reject_duplicate_aliases(bind) -> None:
    duplicates = bind.execute(
        sa.text(
            "SELECT chitti_id, lower(alias) AS folded, count(*) "
            "FROM chitti_members "
            "WHERE alias IS NOT NULL "
            "GROUP BY chitti_id, lower(alias) HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates:
        raise RuntimeError(
            "Cannot add case-insensitive alias uniqueness: Chitti "
            f"{duplicates[0]} already has {duplicates[2]} slots whose aliases "
            f"fold to '{duplicates[1]}'. Resolve the historical aliases manually; "
            "this migration does not rewrite history."
        )


def _reject_duplicate_agreements(bind) -> None:
    duplicates = bind.execute(
        sa.text(
            "SELECT chitti_member_id, count(*) FROM chitti_agreements "
            "GROUP BY chitti_member_id HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates:
        raise RuntimeError(
            "Cannot add one-agreement-per-membership uniqueness: member "
            f"{duplicates[0]} already has {duplicates[1]} agreement rows. "
            "Resolve the historical agreements manually; this migration does "
            "not delete history."
        )


def upgrade() -> None:
    bind = op.get_bind()

    # Lift uniqueness follows the membership slot, not the whole Chitti.
    if _index_columns(bind, LIFT_TABLE, LIFT_INDEX) == LIFT_OLD_COLUMNS:
        op.drop_index(LIFT_INDEX, table_name=LIFT_TABLE)
    if _index_columns(bind, LIFT_TABLE, LIFT_INDEX) != LIFT_NEW_COLUMNS:
        if _index_columns(bind, LIFT_TABLE, LIFT_INDEX) is not None:
            raise RuntimeError(f"Unexpected definition of index {LIFT_INDEX}.")
        op.create_index(
            LIFT_INDEX, LIFT_TABLE, list(LIFT_NEW_COLUMNS),
            unique=True, postgresql_where=sa.text(LIFT_PREDICATE),
        )

    # Alias uniqueness is case-insensitive. The old exact-match index is
    # redundant once this one exists.
    _reject_duplicate_aliases(bind)
    if _index_columns(bind, MEMBER_TABLE, ALIAS_INDEX) is not None:
        op.drop_index(ALIAS_INDEX, table_name=MEMBER_TABLE)
    if _index_columns(bind, MEMBER_TABLE, ALIAS_CI_INDEX) is None:
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_chitti_member_alias_ci "
            "ON chitti_members (chitti_id, lower(alias)) WHERE alias IS NOT NULL"
        )

    # Concurrent agreement generation must not create a second document for
    # the same membership slot.
    _reject_duplicate_agreements(bind)
    if not _has_constraint(bind, AGREEMENT_TABLE, AGREEMENT_CONSTRAINT):
        op.create_unique_constraint(
            AGREEMENT_CONSTRAINT, AGREEMENT_TABLE, ["chitti_member_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_constraint(bind, AGREEMENT_TABLE, AGREEMENT_CONSTRAINT):
        op.drop_constraint(AGREEMENT_CONSTRAINT, AGREEMENT_TABLE, type_="unique")

    if _index_columns(bind, MEMBER_TABLE, ALIAS_CI_INDEX) is not None:
        op.drop_index(ALIAS_CI_INDEX, table_name=MEMBER_TABLE)
    if _index_columns(bind, MEMBER_TABLE, ALIAS_INDEX) is None:
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_chitti_member_alias "
            "ON chitti_members (chitti_id, alias) WHERE alias IS NOT NULL"
        )

    if _index_columns(bind, LIFT_TABLE, LIFT_INDEX) == LIFT_NEW_COLUMNS:
        op.drop_index(LIFT_INDEX, table_name=LIFT_TABLE)
    if _index_columns(bind, LIFT_TABLE, LIFT_INDEX) is None:
        op.create_index(
            LIFT_INDEX, LIFT_TABLE, list(LIFT_OLD_COLUMNS),
            unique=True, postgresql_where=sa.text(LIFT_PREDICATE),
        )
