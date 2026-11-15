"""Add auditable Chitti lift events, separate from payouts.

Revision ID: 0002_lift_events
Revises: 0001_baseline
Create Date: 2026-11-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_lift_events"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chitti_lift_events",
        sa.Column("chitti_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("lift_date", sa.Date(), nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["chitti_id"], ["chittis.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["chitti_members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reversed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chitti_lift_events_id"), "chitti_lift_events", ["id"], unique=False)
    op.create_index(
        "uq_chitti_lift_period_active", "chitti_lift_events",
        ["chitti_id", "period_number"], unique=True,
        postgresql_where=sa.text("reversed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_chitti_lift_period_active", table_name="chitti_lift_events")
    op.drop_index(op.f("ix_chitti_lift_events_id"), table_name="chitti_lift_events")
    op.drop_table("chitti_lift_events")
