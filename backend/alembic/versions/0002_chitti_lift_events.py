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


LIFT_EVENT_COLUMNS = {
    "id": ("UUID", False),
    "chitti_id": ("UUID", False),
    "member_id": ("UUID", False),
    "period_number": ("INTEGER", False),
    "lift_date": ("DATE", False),
    "recorded_by": ("UUID", True),
    "reversed_at": ("TIMESTAMP WITH TIME ZONE", True),
    "reversed_by": ("UUID", True),
    "reversal_reason": ("TEXT", True),
    "created_at": ("TIMESTAMP WITH TIME ZONE", False),
    "updated_at": ("TIMESTAMP WITH TIME ZONE", False),
}
LIFT_EVENT_FOREIGN_KEYS = (
    ("chitti_id", "chittis", "id", "CASCADE"),
    ("member_id", "chitti_members", "id", "RESTRICT"),
    ("recorded_by", "users", "id", "SET NULL"),
    ("reversed_by", "users", "id", "SET NULL"),
)
LIFT_EVENT_INDEXES = {
    "ix_chitti_lift_events_id": (("id",), False, None),
    "uq_chitti_lift_period_active": (
        ("chitti_id", "period_number"),
        True,
        "reversed_at IS NULL",
    ),
}


def _normalize_sql(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum() or char == "_")


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


def _validate_existing_lift_event_table(bind) -> None:
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("chitti_lift_events")}
    missing_columns = set(LIFT_EVENT_COLUMNS) - set(columns)
    if missing_columns:
        raise RuntimeError(
            "Existing chitti_lift_events table is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
    for name, (expected_type, expected_nullable) in LIFT_EVENT_COLUMNS.items():
        column = columns[name]
        actual_type = column["type"].compile(dialect=bind.dialect).upper()
        if actual_type != expected_type or column["nullable"] != expected_nullable:
            raise RuntimeError(
                f"Existing chitti_lift_events.{name} is incompatible "
                f"(type={actual_type}, nullable={column['nullable']})."
            )

    primary_key = inspector.get_pk_constraint("chitti_lift_events")
    if primary_key.get("constrained_columns") != ["id"]:
        raise RuntimeError("Existing chitti_lift_events primary key is incompatible.")
    primary_key_state = bind.execute(
        sa.text(
            "SELECT contype, convalidated, condeferrable, condeferred, "
            "pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = :constraint_name "
            "AND conrelid = 'chitti_lift_events'::regclass"
        ),
        {"constraint_name": primary_key.get("name")},
    ).first()
    constraint_type = (
        primary_key_state[0].decode()
        if primary_key_state and isinstance(primary_key_state[0], bytes)
        else (primary_key_state[0] if primary_key_state else None)
    )
    if (
        not primary_key_state
        or constraint_type != "p"
        or not primary_key_state[1]
        or primary_key_state[2]
        or primary_key_state[3]
        or _normalize_sql(primary_key_state[4]) != _normalize_sql("PRIMARY KEY (id)")
    ):
        raise RuntimeError("Existing chitti_lift_events primary key is incompatible.")

    foreign_keys = inspector.get_foreign_keys("chitti_lift_events")
    expected_foreign_key_columns = {
        (local_column,)
        for local_column, _, _, _ in LIFT_EVENT_FOREIGN_KEYS
    }
    if {
        tuple(foreign_key.get("constrained_columns") or ())
        for foreign_key in foreign_keys
    } != expected_foreign_key_columns:
        raise RuntimeError("Existing chitti_lift_events foreign keys are incompatible.")

    for local_column, target_table, target_column, ondelete in LIFT_EVENT_FOREIGN_KEYS:
        related = [
            foreign_key
            for foreign_key in foreign_keys
            if local_column in (foreign_key.get("constrained_columns") or [])
        ]
        matches = [
            foreign_key
            for foreign_key in related
            if foreign_key.get("constrained_columns") == [local_column]
            and foreign_key.get("referred_table") == target_table
            and foreign_key.get("referred_columns") == [target_column]
            and (foreign_key.get("options") or {}).get("ondelete", "").upper() == ondelete
        ]
        if not matches or len(matches) != len(related):
            raise RuntimeError(
                f"Existing chitti_lift_events foreign key for {local_column} is incompatible."
            )
        for foreign_key in matches:
            constraint_state = bind.execute(
                sa.text(
                    "SELECT convalidated, condeferrable, condeferred "
                    "FROM pg_constraint "
                    "WHERE conname = :constraint_name "
                    "AND conrelid = 'chitti_lift_events'::regclass"
                ),
                {"constraint_name": foreign_key["name"]},
            ).first()
            if not constraint_state or not constraint_state[0] or constraint_state[1] or constraint_state[2]:
                raise RuntimeError(
                    f"Existing chitti_lift_events foreign key for {local_column} is incompatible."
                )

    if inspector.get_check_constraints("chitti_lift_events"):
        raise RuntimeError("Existing chitti_lift_events CHECK constraints are incompatible.")
    if inspector.get_unique_constraints("chitti_lift_events"):
        raise RuntimeError("Existing chitti_lift_events unique constraints are incompatible.")

    indexes = {index["name"]: index for index in inspector.get_indexes("chitti_lift_events")}
    for name, (expected_columns, expected_unique, expected_where) in LIFT_EVENT_INDEXES.items():
        index = indexes.get(name)
        if not index:
            raise RuntimeError(f"Existing chitti_lift_events index {name} is missing.")
        actual_where = (index.get("dialect_options") or {}).get("postgresql_where")
        if (
            tuple(index.get("column_names") or ()) != expected_columns
            or bool(index.get("unique")) != expected_unique
            or _normalize_sql(str(actual_where or ""))
            != _normalize_sql(expected_where or "")
        ):
            raise RuntimeError(f"Existing chitti_lift_events index {name} is incompatible.")
        state = _index_state(bind, name)
        if (
            not state
            or state[0] is not True
            or state[1] is not True
            or bool(state[2]) != expected_unique
            or state[3] != len(expected_columns)
            or state[4] != len(expected_columns)
            or state[5] != "btree"
            or _normalize_sql(str(state[6] or ""))
            != _normalize_sql(expected_where or "")
        ):
            raise RuntimeError(f"Existing chitti_lift_events index {name} is not valid.")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chitti_lift_events" in inspector.get_table_names():
        _validate_existing_lift_event_table(bind)
        return

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
    bind.execute(
        sa.text(
            "COMMENT ON TABLE chitti_lift_events "
            "IS 'owned-by-0002-lift-events'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chitti_lift_events" not in inspector.get_table_names():
        return
    owner = bind.execute(
        sa.text(
            "SELECT obj_description("
            "'chitti_lift_events'::regclass, 'pg_class')"
        )
    ).scalar()
    if owner != "owned-by-0002-lift-events":
        return
    _validate_existing_lift_event_table(bind)
    if bind.execute(
        sa.text("SELECT 1 FROM chitti_lift_events LIMIT 1")
    ).first():
        raise RuntimeError(
            "Refusing to downgrade 0002: chitti_lift_events contains lift history."
        )
    op.drop_index("uq_chitti_lift_period_active", table_name="chitti_lift_events")
    op.drop_index(op.f("ix_chitti_lift_events_id"), table_name="chitti_lift_events")
    op.drop_table("chitti_lift_events")
