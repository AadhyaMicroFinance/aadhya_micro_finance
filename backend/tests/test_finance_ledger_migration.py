"""Revision 0010 must scope the Finance ledger without rewriting history."""

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

REVISION = "0010_finance_ledger_scope"
PREVIOUS = "0009_customer_mobile_uniqueness"


async def _payment_columns(test_url) -> set[str]:
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.connect() as connection:
            return set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'payment_transactions'"
                        )
                    )
                ).scalars().all()
            )
    finally:
        await engine.dispose()


async def _finance_payment_count(test_url) -> int:
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.connect() as connection:
            return int(
                (
                    await connection.execute(
                        text("SELECT count(*) FROM payment_transactions")
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()


async def _create_legacy_schema(test_url) -> None:
    """Baseline metadata plus the pre-0010 Chitti columns on the Finance ledger."""
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
            await connection.exec_driver_sql("CREATE SCHEMA public")
        await _run_migration(command.upgrade, _migration_config(test_url), PREVIOUS)
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "ALTER TABLE payment_transactions "
                "ADD COLUMN chitti_account_id UUID REFERENCES chittis(id) ON DELETE SET NULL"
            )
            await connection.exec_driver_sql(
                "ALTER TABLE payment_transactions "
                "ADD COLUMN chitti_schedule_id UUID "
                "REFERENCES chitti_period_schedule(id) ON DELETE SET NULL"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_0010_upgrade_downgrade_preserves_finance_history():
    test_url = os.environ["TEST_DATABASE_URL"]
    await _reset_migration_schema(test_url)
    config = _migration_config(test_url)
    try:
        await _create_legacy_schema(test_url)
        columns_before = await _payment_columns(test_url)
        assert "chitti_account_id" in columns_before
        assert "chitti_schedule_id" in columns_before

        # Seed a genuine Finance repayment before the structural change.
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as connection:
                customer_id = str(uuid.uuid4())
                await connection.execute(
                    text(
                        "INSERT INTO customers "
                        "(id, customer_code, full_name, mobile_number, status, created_at, updated_at) "
                        "VALUES (CAST(:id AS uuid), :code, :name, :mobile, 'ACTIVE', now(), now())"
                    ),
                    {
                        "id": customer_id,
                        "code": "CUS-MIGRATION",
                        "name": "Migration Finance Payer",
                        "mobile": "9100000099",
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO payment_transactions "
                        "(id, transaction_id, idempotency_key, customer_id, amount, "
                        "payment_method, payment_date, status, is_reversal, created_at, updated_at) "
                        "VALUES (CAST(:id AS uuid), :txn, :key, CAST(:customer AS uuid), 100.00, "
                        "'CASH', CURRENT_DATE, 'COMPLETED', false, now(), now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "txn": "PAY-MIGRATION-000001",
                        "key": "migration-finance-payment",
                        "customer": customer_id,
                    },
                )
        finally:
            await engine.dispose()

        assert await _finance_payment_count(test_url) == 1

        await _run_migration(command.upgrade, config, REVISION)
        columns_after = await _payment_columns(test_url)
        assert "chitti_account_id" not in columns_after
        assert "chitti_schedule_id" not in columns_after
        assert "finance_account_id" in columns_after
        assert "finance_schedule_id" in columns_after
        assert await _finance_payment_count(test_url) == 1

        await _run_migration(command.downgrade, config, PREVIOUS)
        columns_restored = await _payment_columns(test_url)
        assert "chitti_account_id" in columns_restored
        assert "chitti_schedule_id" in columns_restored
        assert await _finance_payment_count(test_url) == 1
    finally:
        await _reset_migration_schema(test_url)
