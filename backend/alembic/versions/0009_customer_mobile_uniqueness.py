"""Customer mobile uniqueness.

Revision ID: 0009_customer_mobile_uniqueness
Revises: 0008_multi_slot_integrity

Adds a database-level guarantee that the same dialled mobile number cannot be
registered twice, including formatted variants such as +91 98765-43210. This
migration never rewrites or deletes customer history: if conflicting data
already exists it fails and asks for a manual decision.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_customer_mobile_uniqueness"
down_revision: Union[str, None] = "0008_multi_slot_integrity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "customers"
INDEX = "uq_customer_mobile_digits"


def _has_index(bind) -> bool:
    return any(
        item.get("name") == INDEX
        for item in sa.inspect(bind).get_indexes(TABLE)
    )


def _reject_duplicate_mobiles(bind) -> None:
    duplicate = bind.execute(
        sa.text(
            "SELECT regexp_replace(mobile_number, '\\D', '', 'g') AS digits, count(*) "
            "FROM customers GROUP BY digits HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "Cannot add unique customer mobile index: "
            f"{duplicate[1]} customers share digits '{duplicate[0]}'. "
            "Resolve the historical records manually; this migration does not "
            "rewrite or delete history."
        )


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        raise RuntimeError("customers table does not exist; apply the baseline first.")
    if _has_index(bind):
        return
    _reject_duplicate_mobiles(bind)
    op.execute(
        f"CREATE UNIQUE INDEX {INDEX} ON {TABLE} "
        f"(regexp_replace(mobile_number, '\\D', '', 'g'))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or not _has_index(bind):
        return
    op.drop_index(INDEX, table_name=TABLE)
