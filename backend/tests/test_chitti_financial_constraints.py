"""PostgreSQL CHECK constraint tests for Chitti financial tables."""

import os
import uuid
import asyncio
from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.chitti import (
    Chitti,
    ChittiMember,
    ChittiMemberContribution,
    ChittiPeriodSchedule,
    ChittiPlan,
    ChittiPayout,
    ChittiTransaction,
)
from app.models.customer import Customer


CONSTRAINT_NAMES = (
    "ck_chitti_contribution_expected_amount_nonnegative",
    "ck_chitti_contribution_paid_amount_nonnegative",
    "ck_chitti_contribution_remaining_amount_nonnegative",
    "ck_chitti_period_expected_collection_nonnegative",
    "ck_chitti_period_actual_collection_nonnegative",
    "ck_chitti_period_pending_collection_nonnegative",
    "ck_chitti_period_expected_payout_nonnegative",
    "ck_chitti_period_actual_payout_nonnegative",
    "ck_chitti_payout_gross_nonnegative",
    "ck_chitti_payout_discount_nonnegative",
    "ck_chitti_payout_fee_nonnegative",
    "ck_chitti_payout_net_nonnegative",
    "ck_chitti_payout_net_arithmetic",
    "ck_chitti_transaction_amount_nonnegative",
)


async def _make_chitti_fixture(db_session):
    customer = Customer(
        customer_code=f"CUS-{uuid.uuid4().hex[:8]}",
        full_name="Constraint Test Member",
        mobile_number=f"9{uuid.uuid4().int % 10**9:09d}",
        status="ACTIVE",
    )
    db_session.add(customer)

    plan = ChittiPlan(
        plan_code=f"PLN-{uuid.uuid4().hex[:8]}",
        name="Constraint Test Lift Plan",
        chitti_type="LIFT_BASED",
        total_value=Decimal("120000"),
        member_count=1,
        frequency="DAILY",
        duration=4,
        contribution_rules={
            "type": "LIFT_BASED",
            "regular_amount": "5000",
        },
        payout_rules={
            "type": "SCHEDULED",
            "payout_order": "MEMBER_NUMBER",
        },
        is_active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    chitti = Chitti(
        chitti_code=f"CHT-{uuid.uuid4().hex[:8]}",
        plan_id=plan.id,
        plan_snapshot={
            "chitti_type": "LIFT_BASED",
            "total_value": "120000",
            "member_count": 1,
            "frequency": "DAILY",
            "duration": 4,
            "contribution_rules": {
                "type": "LIFT_BASED",
                "regular_amount": "5000",
            },
            "payout_rules": {
                "type": "SCHEDULED",
                "payout_order": "MEMBER_NUMBER",
            },
        },
        name="Constraint Test Chitti",
        start_date=date.today(),
        end_date=date.today(),
        member_count=1,
        total_value=Decimal("120000"),
        status="RUNNING",
    )
    db_session.add(chitti)
    await db_session.flush()

    member = ChittiMember(
        chitti_id=chitti.id,
        customer_id=customer.id,
        member_number=1,
        payout_order=1,
        status="ACTIVE",
        total_expected_amount=Decimal("0"),
        total_paid_amount=Decimal("0"),
        outstanding_amount=Decimal("0"),
        lifted=False,
    )
    db_session.add(member)
    await db_session.flush()
    return chitti, member


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("expected_amount", Decimal("-1")),
        ("paid_amount", Decimal("-1")),
        ("remaining_amount", Decimal("-1")),
    ],
)
async def test_negative_member_contribution_amount_rejected(
    db_session, field_name, invalid_value
):
    chitti, member = await _make_chitti_fixture(db_session)
    values = {
        "chitti_id": chitti.id,
        "member_id": member.id,
        "period_number": 1,
        "expected_amount": Decimal("100"),
        "paid_amount": Decimal("0"),
        "remaining_amount": Decimal("100"),
    }
    values[field_name] = invalid_value

    db_session.add(ChittiMemberContribution(**values))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("expected_collection", Decimal("-1")),
        ("actual_collection", Decimal("-1")),
        ("pending_collection", Decimal("-1")),
        ("expected_payout", Decimal("-1")),
        ("actual_payout", Decimal("-1")),
    ],
)
async def test_negative_period_amount_rejected(db_session, field_name, invalid_value):
    chitti, _ = await _make_chitti_fixture(db_session)
    values = {
        "chitti_id": chitti.id,
        "period_number": 1,
        "due_date": date.today(),
        "expected_collection": Decimal("100"),
        "actual_collection": Decimal("0"),
        "pending_collection": Decimal("100"),
        "expected_payout": Decimal("0"),
        "actual_payout": Decimal("0"),
        "status": "UPCOMING",
    }
    values[field_name] = invalid_value

    db_session.add(ChittiPeriodSchedule(**values))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("gross_payout", Decimal("-1")),
        ("discount_amount", Decimal("-1")),
        ("fee_amount", Decimal("-1")),
        ("net_payout", Decimal("-1")),
    ],
)
async def test_negative_payout_amount_rejected(db_session, field_name, invalid_value):
    chitti, member = await _make_chitti_fixture(db_session)
    values = {
        "chitti_id": chitti.id,
        "member_id": member.id,
        "period_number": 1,
        "gross_payout": Decimal("100"),
        "discount_amount": Decimal("10"),
        "fee_amount": Decimal("5"),
        "net_payout": Decimal("85"),
        "payout_method": "CASH",
        "status": "PAID",
    }
    values[field_name] = invalid_value

    db_session.add(ChittiPayout(**values))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_payout_net_arithmetic_mismatch_rejected(db_session):
    chitti, member = await _make_chitti_fixture(db_session)
    db_session.add(ChittiPayout(
        chitti_id=chitti.id,
        member_id=member.id,
        period_number=1,
        gross_payout=Decimal("100"),
        discount_amount=Decimal("10"),
        fee_amount=Decimal("5"),
        net_payout=Decimal("84"),
        payout_method="CASH",
        status="PAID",
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_negative_ledger_amount_rejected(db_session):
    chitti, member = await _make_chitti_fixture(db_session)
    db_session.add(ChittiTransaction(
        chitti_id=chitti.id,
        member_id=member.id,
        transaction_type="CONTRIBUTION",
        amount=Decimal("-1"),
        payment_method="CASH",
        period_number=1,
        idempotency_key=f"negative-ledger-{uuid.uuid4()}",
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_zero_values_accepted(db_session):
    chitti, member = await _make_chitti_fixture(db_session)
    db_session.add_all([
        ChittiMemberContribution(
            chitti_id=chitti.id,
            member_id=member.id,
            period_number=1,
            expected_amount=Decimal("0"),
            paid_amount=Decimal("0"),
            remaining_amount=Decimal("0"),
            status="UPCOMING",
        ),
        ChittiPeriodSchedule(
            chitti_id=chitti.id,
            period_number=1,
            due_date=date.today(),
            expected_collection=Decimal("0"),
            actual_collection=Decimal("0"),
            pending_collection=Decimal("0"),
            expected_payout=Decimal("0"),
            actual_payout=Decimal("0"),
            status="UPCOMING",
        ),
        ChittiPayout(
            chitti_id=chitti.id,
            member_id=member.id,
            period_number=1,
            gross_payout=Decimal("0"),
            discount_amount=Decimal("0"),
            fee_amount=Decimal("0"),
            net_payout=Decimal("0"),
            payout_method="CASH",
            status="PAID",
        ),
        ChittiTransaction(
            chitti_id=chitti.id,
            member_id=member.id,
            transaction_type="CONTRIBUTION",
            amount=Decimal("0"),
            payment_method="CASH",
            period_number=1,
            idempotency_key=f"zero-ledger-{uuid.uuid4()}",
        ),
    ])
    await db_session.flush()


@pytest.mark.asyncio
async def test_lift_overpayment_values_remain_allowed(db_session):
    chitti, member = await _make_chitti_fixture(db_session)
    db_session.add(ChittiMemberContribution(
        chitti_id=chitti.id,
        member_id=member.id,
        period_number=1,
        expected_amount=Decimal("100"),
        paid_amount=Decimal("150"),
        remaining_amount=Decimal("0"),
        status="PAID",
    ))
    await db_session.flush()


@pytest.mark.asyncio
async def test_migration_upgrade_downgrade_symmetry():
    from tests.conftest import _assert_scratch_database

    _assert_scratch_database()
    test_url = os.environ["TEST_DATABASE_URL"]

    engine = create_async_engine(test_url, echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.exec_driver_sql("CREATE SCHEMA public")
    await engine.dispose()

    os.environ["DATABASE_URL"] = test_url
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_url)
    config.set_main_option("script_location", "alembic")

    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(test_url, echo=False)
    names_sql = ", ".join(f"'{name}'" for name in CONSTRAINT_NAMES)
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT conname FROM pg_constraint "
            f"WHERE conname IN ({names_sql})"
        ))).all()
        assert {row[0] for row in rows} == set(CONSTRAINT_NAMES)
    await engine.dispose()

    await asyncio.to_thread(command.downgrade, config, "0002_lift_events")

    engine = create_async_engine(test_url, echo=False)
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT conname FROM pg_constraint "
            f"WHERE conname IN ({names_sql})"
        ))).all()
        assert rows == []
    await engine.dispose()

    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(test_url, echo=False)
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT conname FROM pg_constraint "
            f"WHERE conname IN ({names_sql})"
        ))).all()
        assert {row[0] for row in rows} == set(CONSTRAINT_NAMES)
    await engine.dispose()
