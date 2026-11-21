"""Revision 0009 must add mobile uniqueness without rewriting customer history."""

import os
import uuid

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.test_chitti_financial_constraints import (
    _migration_config,
    _reset_migration_schema,
    _run_migration,
)


INDEX = "uq_customer_mobile_digits"


async def _index_exists(test_url) -> bool:
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT to_regclass(:name) IS NOT NULL"), {"name": INDEX}
                )
            ).scalar()
            return bool(row)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_0009_upgrade_downgrade_reupgrade():
    test_url = os.environ["TEST_DATABASE_URL"]
    await _reset_migration_schema(test_url)
    config = _migration_config(test_url)

    await _run_migration(command.upgrade, config, "head")
    assert await _index_exists(test_url)

    await _run_migration(command.downgrade, config, "0008_multi_slot_integrity")
    assert not await _index_exists(test_url)

    await _run_migration(command.upgrade, config, "head")
    assert await _index_exists(test_url)


@pytest.mark.asyncio
async def test_0009_rejects_conflicting_history_without_deleting_rows():
    test_url = os.environ["TEST_DATABASE_URL"]
    await _reset_migration_schema(test_url)
    config = _migration_config(test_url)

    await _run_migration(command.upgrade, config, "0008_multi_slot_integrity")
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.begin() as conn:
            # The baseline currently carries the index; remove it to simulate
            # an older installation before adding conflicting history.
            await conn.exec_driver_sql(f"DROP INDEX IF EXISTS {INDEX}")
            for suffix in ("a", "b"):
                await conn.execute(
                    text(
                        "INSERT INTO customers "
                        "(id, customer_code, full_name, mobile_number, status, created_at, updated_at) "
                        "VALUES (CAST(:id AS uuid), :code, :name, :mobile, 'ACTIVE', now(), now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "code": f"CUS-OLD-{suffix}",
                        "name": f"Legacy Customer {suffix}",
                        "mobile": "+91 98765-43210",
                    },
                )
    finally:
        await engine.dispose()

    with pytest.raises(RuntimeError, match="Resolve the historical records manually"):
        await _run_migration(command.upgrade, config, "head")

    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.connect() as conn:
            count = (
                await conn.execute(text("SELECT count(*) FROM customers"))
            ).scalar()
            assert count == 2
    finally:
        await engine.dispose()
