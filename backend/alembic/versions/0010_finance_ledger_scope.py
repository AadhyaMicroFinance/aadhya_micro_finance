"""Scope payment_transactions to the Finance module.

Revision ID: 0010_finance_ledger_scope
Revises: 0009_customer_mobile_uniqueness

Finance and Money Budget Schemes must keep independent transaction ledgers.
Chitti money is already recorded in ``chitti_transactions``; this revision
removes the legacy Chitti foreign keys from the Finance repayment ledger so the
database schema can no longer mix the two streams.

The migration refuses to rewrite or delete history. If legacy rows still point
at Chitti records, they must be reviewed and migrated manually first.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010_finance_ledger_scope"
down_revision: Union[str, None] = "0009_customer_mobile_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "payment_transactions"
CHITTI_COLUMNS = ("chitti_account_id", "chitti_schedule_id")


def _columns(bind) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(bind).get_columns(TABLE)
    }


def _reject_legacy_chitti_rows(bind) -> None:
    row = bind.execute(
        sa.text(
            "SELECT count(*) FROM payment_transactions "
            "WHERE chitti_account_id IS NOT NULL OR chitti_schedule_id IS NOT NULL"
        )
    ).scalar_one()
    if row:
        raise RuntimeError(
            f"Cannot scope payment_transactions to Finance: {row} legacy row(s) "
            "still reference Chitti records. Move them to chitti_transactions "
            "manually; this migration never rewrites financial history."
        )


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        raise RuntimeError("payment_transactions does not exist; apply the baseline first.")

    present = _columns(bind)
    if not any(column in present for column in CHITTI_COLUMNS):
        return
    if "chitti_account_id" in present or "chitti_schedule_id" in present:
        _reject_legacy_chitti_rows(bind)

    if "chitti_schedule_id" in present:
        op.drop_column(TABLE, "chitti_schedule_id")
    if "chitti_account_id" in present:
        op.drop_column(TABLE, "chitti_account_id")


def downgrade() -> None:
    bind = op.get_bind()
    present = _columns(bind)
    if any(column in present for column in CHITTI_COLUMNS):
        return

    uuid_type = postgresql.UUID(as_uuid=True)
    op.add_column(TABLE, sa.Column("chitti_account_id", uuid_type, nullable=True))
    op.add_column(TABLE, sa.Column("chitti_schedule_id", uuid_type, nullable=True))
    op.create_foreign_key(
        "fk_payment_chitti_account",
        TABLE,
        "chittis",
        ["chitti_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_payment_chitti_schedule",
        TABLE,
        "chitti_period_schedule",
        ["chitti_schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )
