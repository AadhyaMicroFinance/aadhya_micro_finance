"""Revision 0008 must upgrade/downgrade safely without rewriting history."""

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.chitti import (
    Chitti,
    ChittiAgreement,
    ChittiLiftEvent,
    ChittiMember,
    ChittiPlan,
)
from app.models.customer import Customer
from tests.test_chitti_financial_constraints import (
    _migration_config,
    _reset_migration_schema,
    _run_migration,
    _verify_database_identity,
)


PREVIOUS_REVISION = "0007_chitti_credit_resolution"


def _sessions(test_url):
    return async_sessionmaker(
        create_async_engine(test_url, echo=False),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _seed_history(session, *, second_alias="Slot B", duplicate_agreement=False):
    customer = Customer(
        customer_code=f"CUS-{uuid.uuid4().hex[:8]}",
        full_name="Migration Slot Member",
        mobile_number=f"9{uuid.uuid4().int % 10**9:09d}",
        status="ACTIVE",
    )
    plan = ChittiPlan(
        plan_code=f"PLN-{uuid.uuid4().hex[:8]}",
        name="Migration Slot Plan",
        chitti_type="LIFT_BASED",
        total_value=Decimal("200000"),
        member_count=2,
        frequency="DAILY",
        duration=4,
        contribution_rules={"type": "LIFT_BASED", "regular_amount": "5000"},
        payout_rules={"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
        is_active=True,
    )
    session.add_all((customer, plan))
    await session.flush()

    snapshot = {
        "chitti_type": "LIFT_BASED",
        "total_value": "200000",
        "member_count": 2,
        "frequency": "DAILY",
        "duration": 4,
        "contribution_rules": {"type": "LIFT_BASED", "regular_amount": "5000"},
        "payout_rules": {"type": "SCHEDULED", "payout_order": "MEMBER_NUMBER"},
    }
    chitti = Chitti(
        chitti_code=f"CHT-{uuid.uuid4().hex[:8]}",
        plan_id=plan.id,
        plan_snapshot=snapshot,
        name="Migration Slot Chitti",
        start_date=date.today(),
        end_date=date.today(),
        member_count=2,
        total_value=Decimal("200000"),
        status="RUNNING",
    )
    session.add(chitti)
    await session.flush()

    # Same customer in two slots: the exact scenario that per-slot history must
    # preserve.
    members = [
        ChittiMember(
            chitti_id=chitti.id,
            customer_id=customer.id,
            alias=alias,
            member_number=number,
            payout_order=number,
            status="ACTIVE",
        )
        for number, alias in enumerate(("Slot A", second_alias), start=1)
    ]
    session.add_all(members)
    await session.flush()

    lifts = [
        ChittiLiftEvent(
            chitti_id=chitti.id,
            member_id=member.id,
            period_number=number,
            lift_date=date.today(),
        )
        for number, member in enumerate(members, start=1)
    ]
    session.add_all(lifts)

    agreements = [
        ChittiAgreement(
            agreement_number=f"AGR-MIG-{uuid.uuid4().hex[:10]}",
            chitti_id=chitti.id,
            chitti_member_id=members[0].id,
            customer_id=customer.id,
            agreement_date=date.today(),
            agreement_status="CONFIRMED",
            agreement_snapshot={"slot": "Slot A"},
        )
    ]
    if duplicate_agreement:
        agreements.append(ChittiAgreement(
            agreement_number=f"AGR-MIG-{uuid.uuid4().hex[:10]}",
            chitti_id=chitti.id,
            chitti_member_id=members[0].id,
            customer_id=customer.id,
            agreement_date=date.today(),
            agreement_status="PRINTED",
            agreement_snapshot={"slot": "Slot A duplicate"},
        ))
    session.add_all(agreements)
    await session.commit()
    return chitti.id, customer.id, [m.id for m in members], [lift.id for lift in lifts]


async def _make_pre_0008_schema(test_url):
    """Recreate the schema revision 0007 actually shipped.

    The 0001 baseline is built from current model metadata, so a fresh upgrade
    to 0007 already contains 0008's indexes/constraint. Tests must explicitly
    revert those objects to exercise 0008's upgrade path.
    """
    await _verify_database_identity(test_url)
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                "DROP INDEX IF EXISTS uq_chitti_member_alias_ci"
            )
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_chitti_member_alias "
                "ON chitti_members (chitti_id, alias) WHERE alias IS NOT NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE chitti_agreements "
                "DROP CONSTRAINT IF EXISTS uq_chitti_agreement_member"
            )
            await conn.exec_driver_sql(
                "DROP INDEX IF EXISTS uq_chitti_lift_period_active"
            )
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_chitti_lift_period_active "
                "ON chitti_lift_events (chitti_id, period_number) "
                "WHERE reversed_at IS NULL"
            )
    finally:
        await engine.dispose()


async def _index_definition(test_url, name, table):
    await _verify_database_identity(test_url)
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = current_schema() "
                    "AND indexname = :name AND tablename = :table"
                ),
                {"name": name, "table": table},
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_0008_upgrade_downgrade_preserves_history_and_uses_slot_lift_index():
    test_url = os.environ["TEST_DATABASE_URL"]
    await _reset_migration_schema(test_url)
    config = _migration_config(test_url)
    try:
        await _run_migration(command.upgrade, config, PREVIOUS_REVISION)
        await _make_pre_0008_schema(test_url)
        maker = _sessions(test_url)
        engine = maker.kw["bind"]
        try:
            async with maker() as session:
                chitti_id, customer_id, member_ids, lift_ids = await _seed_history(session)
        finally:
            await engine.dispose()

        await _run_migration(command.upgrade, config, "head")

        lift_index = await _index_definition(
            test_url, "uq_chitti_lift_period_active", "chitti_lift_events"
        )
        assert "chitti_id, member_id, period_number" in lift_index
        alias_index = await _index_definition(
            test_url, "uq_chitti_member_alias_ci", "chitti_members"
        )
        assert "lower" in alias_index and "alias" in alias_index
        await _verify_database_identity(test_url)
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.connect() as conn:
                assert await conn.scalar(
                    text("SELECT count(*) FROM chitti_lift_events")
                ) == 2
                assert await conn.scalar(
                    text("SELECT count(*) FROM chitti_payment_allocations")
                ) == 0
                assert await conn.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname = 'uq_chitti_agreement_member' "
                        "AND contype = 'u'"
                    )
                ) == 1
                stored = (
                    await conn.execute(
                        text(
                            "SELECT chitti_id, member_number, alias FROM chitti_members "
                            "ORDER BY member_number"
                        )
                    )
                ).all()
                assert [row[0] for row in stored] == [chitti_id, chitti_id]
                assert [row[1] for row in stored] == [1, 2]
                assert [row[2] for row in stored] == ["Slot A", "Slot B"]
        finally:
            await engine.dispose()

        # Two slots of the same customer can now lift in the same period.
        maker = _sessions(test_url)
        engine = maker.kw["bind"]
        try:
            async with maker() as session:
                session.add(ChittiLiftEvent(
                    chitti_id=chitti_id,
                    member_id=member_ids[1],
                    period_number=1,
                    lift_date=date.today(),
                ))
                await session.commit()
                session.add(ChittiLiftEvent(
                    chitti_id=chitti_id,
                    member_id=member_ids[0],
                    period_number=1,
                    lift_date=date.today(),
                ))
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()
        finally:
            await engine.dispose()

        # Make the extra row valid for the old global-period index before
        # downgrading; this only changes synthetic test data.
        maker = _sessions(test_url)
        engine = maker.kw["bind"]
        try:
            async with maker() as session:
                rows = (
                    await session.execute(
                        select(ChittiLiftEvent).where(
                            ChittiLiftEvent.member_id == member_ids[1],
                            ChittiLiftEvent.period_number == 1,
                        )
                    )
                ).scalars().all()
                for row in rows:
                    row.reversed_at = date.today()
                await session.commit()
        finally:
            await engine.dispose()

        await _run_migration(command.downgrade, config, PREVIOUS_REVISION)
        lift_index = await _index_definition(
            test_url, "uq_chitti_lift_period_active", "chitti_lift_events"
        )
        assert "chitti_id, period_number" in lift_index
        assert "member_id" not in lift_index
        assert await _index_definition(
            test_url, "uq_chitti_member_alias_ci", "chitti_members"
        ) is None
        assert await _index_definition(
            test_url, "uq_chitti_member_alias", "chitti_members"
        ) is not None
        await _verify_database_identity(test_url)
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.connect() as conn:
                remaining = {
                    str(value) for value in (
                        await conn.execute(text("SELECT id FROM chitti_lift_events"))
                    ).scalars().all()
                }
                assert {str(lift_id) for lift_id in lift_ids}.issubset(remaining)
                assert await conn.scalar(text("SELECT count(*) FROM chitti_members")) == 2
        finally:
            await engine.dispose()
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_0008_rejects_case_variant_alias_history():
    test_url = os.environ["TEST_DATABASE_URL"]
    await _reset_migration_schema(test_url)
    config = _migration_config(test_url)
    try:
        await _run_migration(command.upgrade, config, PREVIOUS_REVISION)
        await _make_pre_0008_schema(test_url)
        maker = _sessions(test_url)
        engine = maker.kw["bind"]
        try:
            async with maker() as session:
                await _seed_history(session, second_alias="slot a")
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="case-insensitive alias uniqueness"):
            await _run_migration(command.upgrade, config, "head")

        assert await _index_definition(
            test_url, "uq_chitti_member_alias_ci", "chitti_members"
        ) is None
        await _verify_database_identity(test_url)
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.connect() as conn:
                aliases = (
                    await conn.execute(
                        text("SELECT alias FROM chitti_members ORDER BY member_number")
                    )
                ).scalars().all()
                assert aliases == ["Slot A", "slot a"]
        finally:
            await engine.dispose()
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_0008_rejects_duplicate_agreement_history():
    test_url = os.environ["TEST_DATABASE_URL"]
    await _reset_migration_schema(test_url)
    config = _migration_config(test_url)
    try:
        await _run_migration(command.upgrade, config, PREVIOUS_REVISION)
        await _make_pre_0008_schema(test_url)
        maker = _sessions(test_url)
        engine = maker.kw["bind"]
        try:
            async with maker() as session:
                await _seed_history(session, duplicate_agreement=True)
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="one-agreement-per-membership uniqueness"):
            await _run_migration(command.upgrade, config, "head")

        await _verify_database_identity(test_url)
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.connect() as conn:
                assert await conn.scalar(
                    text("SELECT count(*) FROM chitti_agreements")
                ) == 2
                assert await conn.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname = 'uq_chitti_agreement_member' AND contype = 'u'"
                    )
                ) == 0
        finally:
            await engine.dispose()
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_0008_rejects_conflicting_lift_history_without_deleting_rows():
    test_url = os.environ["TEST_DATABASE_URL"]
    await _reset_migration_schema(test_url)
    config = _migration_config(test_url)
    try:
        await _run_migration(command.upgrade, config, PREVIOUS_REVISION)
        await _make_pre_0008_schema(test_url)
        maker = _sessions(test_url)
        engine = maker.kw["bind"]
        try:
            async with maker() as session:
                chitti_id, _, member_ids, lift_ids = await _seed_history(session)
                await session.execute(
                    text("DROP INDEX uq_chitti_lift_period_active")
                )
                session.add(ChittiLiftEvent(
                    chitti_id=chitti_id,
                    member_id=member_ids[0],
                    period_number=1,
                    lift_date=date.today(),
                ))
                await session.commit()
        finally:
            await engine.dispose()

        with pytest.raises(IntegrityError):
            await _run_migration(command.upgrade, config, "head")

        await _verify_database_identity(test_url)
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.connect() as conn:
                assert await conn.scalar(text("SELECT count(*) FROM chitti_lift_events")) == 3
                ids = {
                    str(value) for value in (
                        await conn.execute(text("SELECT id FROM chitti_lift_events"))
                    ).scalars().all()
                }
                assert {str(value) for value in lift_ids}.issubset(ids)
        finally:
            await engine.dispose()
    finally:
        await _reset_migration_schema(test_url)
