"""baseline: full schema from SQLAlchemy models

The project predates its migration history: earlier revisions only created the
chitti tables and a couple of ledger columns, so a brand-new database could not
be built with `alembic upgrade head` (chitti_plans references a users table that
no migration created). This baseline materialises the complete schema from the
model metadata and replaces those partial revisions.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _metadata():
    # Imported lazily so `alembic` CLI startup stays light.
    import app.models  # noqa: F401  (registers every table on Base.metadata)
    from app.db.database import Base

    return Base.metadata


def upgrade() -> None:
    metadata = _metadata()
    # This baseline predates the explicit lift-event feature. Keep that table
    # in its own additive revision so a fresh upgrade does not create it twice.
    tables = [table for table in metadata.sorted_tables if table.name != "chitti_lift_events"]
    metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade() -> None:
    metadata = _metadata()
    tables = [table for table in metadata.sorted_tables if table.name != "chitti_lift_events"]
    metadata.drop_all(bind=op.get_bind(), tables=tables)
