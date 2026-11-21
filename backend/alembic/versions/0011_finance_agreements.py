"""Finance loan agreements.

Revision ID: 0011_finance_agreements
Revises: 0010_finance_ledger_scope

Adds the Finance-only agreement workflow table. It uses its own status enum so
the Chitti agreement model and its migrations are completely untouched.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_finance_agreements"
down_revision: Union[str, None] = "0010_finance_ledger_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "finance_agreements"
STATUS_ENUM = "finance_agreement_status_enum"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE):
        return

    labels = ("DRAFT", "GENERATED", "PRINTED", "CONFIRMED", "CANCELLED")
    has_type = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": STATUS_ENUM},
    ).first() is not None
    if not has_type:
        postgresql.ENUM(*labels, name=STATUS_ENUM).create(bind, checkfirst=True)
    # The type is created explicitly above; the column must not try again.
    # A plain sa.Enum ignores create_type, so use the PostgreSQL ENUM type here.
    status_type = postgresql.ENUM(*labels, name=STATUS_ENUM, create_type=False)

    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("agreement_number", sa.String(30), nullable=False),
        sa.Column("customer_id", uuid_type, nullable=False),
        sa.Column(
            "agreement_status",
            status_type,
            nullable=False,
            server_default="GENERATED",
        ),
        sa.Column("agreement_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("terms_hash", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("print_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", uuid_type, nullable=True),
        sa.Column("finance_account_id", uuid_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["finance_account_id"], ["finance_accounts.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("finance_account_id", name="uq_finance_agreement_account"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finance_agreements_agreement_number",
        TABLE,
        ["agreement_number"],
        unique=True,
    )
    op.create_index("ix_finance_agreements_terms_hash", TABLE, ["terms_hash"])
    op.create_index("ix_finance_agreements_id", TABLE, ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    op.drop_table(TABLE)
    # The type is not owned by the table (create_type=False), so remove it
    # explicitly to keep repeated upgrade/downgrade cycles clean.
    labels = ("DRAFT", "GENERATED", "PRINTED", "CONFIRMED", "CANCELLED")
    postgresql.ENUM(*labels, name=STATUS_ENUM).drop(bind, checkfirst=True)
