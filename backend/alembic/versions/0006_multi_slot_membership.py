"""P0.6 multi-slot membership: drop customer uniqueness, add alias."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_multi_slot_membership"
down_revision = "0005_chitti_payment_allocations"

def upgrade():
    op.execute("ALTER TABLE chitti_members DROP CONSTRAINT IF EXISTS uq_chitti_member_customer")
    op.execute("ALTER TABLE chitti_members ADD COLUMN IF NOT EXISTS alias VARCHAR(100)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_chitti_member_alias "
        "ON chitti_members (chitti_id, alias) WHERE alias IS NOT NULL"
    )

def downgrade():
    op.drop_index("uq_chitti_member_alias", table_name="chitti_members")
    op.drop_column("chitti_members", "alias")
    op.create_unique_constraint("uq_chitti_member_customer", "chitti_members", ["chitti_id", "customer_id"])
