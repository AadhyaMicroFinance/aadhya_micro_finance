"""PostgreSQL CHECK constraint tests for Chitti financial tables."""

import os
import uuid
import asyncio
import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.db.database import Base
from app.models.chitti import (
    Chitti,
    ChittiLiftEvent,
    ChittiMember,
    ChittiMemberContribution,
    ChittiPaymentAllocation,
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


def _legacy_metadata(include_lift_events=False):
    metadata = MetaData()
    link_columns = {
        "chitti_transactions": "original_transaction_id",
        "chitti_payouts": "ledger_transaction_id",
    }
    for table in Base.metadata.tables.values():
        if table.name not in ("chitti_lift_events", "chitti_payment_allocations"):
            table.to_metadata(metadata)

    for table in metadata.tables.values():
        for constraint in list(table.constraints):
            if constraint.name in CONSTRAINT_NAMES:
                table.constraints.remove(constraint)

        link_column_name = link_columns.get(table.name)
        if link_column_name and link_column_name in table.c:
            column = table.c[link_column_name]
            for constraint in list(table.constraints):
                if any(item.name == link_column_name for item in constraint.columns):
                    table.constraints.remove(constraint)
            for index in list(table.indexes):
                if any(item.name == link_column_name for item in index.columns):
                    table.indexes.remove(index)
            for foreign_key in list(column.foreign_keys):
                column.foreign_keys.remove(foreign_key)
            table._columns.remove(column)

    if include_lift_events:
        ChittiLiftEvent.__table__.to_metadata(metadata)
    return metadata


def _normalize_definition(value):
    value = re.sub(r"\bcheck\b", "", value.lower())
    value = re.sub(r"::\s*(numeric|integer|bigint|smallint|real|double precision)", "", value)
    value = re.sub(r'"([^"]+)"', r"\1", value)
    return "".join(char for char in value if char.isalnum() or char in "_<>=+-")


def _parse_check_expression(definition):
    value = re.sub(r"\bcheck\b", "", definition.lower())
    value = re.sub(r"::\s*(numeric|integer|bigint|smallint|real|double precision)", "", value)
    compact = re.sub(r"\s+", "", value.replace('"', ""))
    tokens = re.findall(
        r"[a-z_][a-z0-9_]*|\d+(?:\.\d+)?|>=|<=|<>|!=|[=()+\-*/]",
        compact,
    )
    assert "".join(tokens) == compact
    position = 0

    def atom():
        nonlocal position
        token = tokens[position]
        if token == "(":
            position += 1
            result = comparison()
            assert tokens[position] == ")"
            position += 1
            return result
        assert token not in (")", "=", ">=", "<=", "<>", "!=", "+", "-", "*", "/")
        position += 1
        return token

    def product():
        nonlocal position
        result = atom()
        while position < len(tokens) and tokens[position] in ("*", "/"):
            operator = tokens[position]
            position += 1
            result = (operator, result, atom())
        return result

    def addition():
        nonlocal position
        result = product()
        while position < len(tokens) and tokens[position] in ("+", "-"):
            operator = tokens[position]
            position += 1
            result = (operator, result, product())
        return result

    def comparison():
        nonlocal position
        result = addition()
        if position < len(tokens) and tokens[position] in ("=", ">=", "<=", "<>", "!="):
            operator = tokens[position]
            position += 1
            result = (operator, result, addition())
        return result

    result = comparison()
    assert position == len(tokens)
    return result


def test_legacy_migration_fixture_excludes_p050_schema_additions():
    metadata = _legacy_metadata()
    assert "chitti_lift_events" not in metadata.tables
    assert "chitti_payment_allocations" not in metadata.tables
    assert "original_transaction_id" not in metadata.tables[
        "chitti_transactions"
    ].c
    assert "ledger_transaction_id" not in metadata.tables["chitti_payouts"].c
    assert not {
        constraint.name
        for table in metadata.tables.values()
        for constraint in table.constraints
    }.intersection(CONSTRAINT_NAMES)


def test_check_expression_comparison_preserves_arithmetic_grouping():
    expected = "CHECK (net_payout = gross_payout - discount_amount - fee_amount)"
    equivalent = "CHECK (((net_payout = ((gross_payout - discount_amount) - fee_amount))))"
    reassociated = "CHECK (net_payout = gross_payout - (discount_amount - fee_amount))"
    assert _parse_check_expression(expected) == _parse_check_expression(equivalent)
    assert _parse_check_expression(expected) != _parse_check_expression(reassociated)


def _assert_test_target(test_url):
    from tests.conftest import _assert_scratch_database

    _assert_scratch_database()
    target = urlparse(test_url)
    assert target.path.rsplit("/", 1)[-1].endswith("_test")
    assert test_url == os.environ["TEST_DATABASE_URL"]


async def _verify_database_identity(test_url):
    _assert_test_target(test_url)
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.connect() as conn:
            database_name = await conn.scalar(text("SELECT current_database()"))
            assert database_name == urlparse(test_url).path.rsplit("/", 1)[-1]
            assert database_name.endswith("_test")
    finally:
        await engine.dispose()


async def _reset_migration_schema(test_url):
    await _verify_database_identity(test_url)
    engine = create_async_engine(test_url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
            await conn.exec_driver_sql("CREATE SCHEMA public")
    finally:
        await engine.dispose()


def _migration_config(test_url):
    os.environ["DATABASE_URL"] = test_url
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_url.replace("%", "%%"))
    config.set_main_option("script_location", "alembic")
    return config


async def _run_migration(operation, config, revision):
    test_url = os.environ["TEST_DATABASE_URL"]
    await _verify_database_identity(test_url)
    await asyncio.to_thread(operation, config, revision)


async def _prepare_migration_schema(include_lift_events=False):
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        from tests.conftest import _assert_scratch_database

        _assert_scratch_database()
    await _reset_migration_schema(test_url)
    engine = create_async_engine(test_url, echo=False)
    try:
        metadata = _legacy_metadata(include_lift_events)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
    finally:
        await engine.dispose()
    config = _migration_config(test_url)
    await _run_migration(command.stamp, config, "0001_baseline")
    return test_url, config


async def _assert_financial_migration_schema(test_url):
    await _verify_database_identity(test_url)
    engine = create_async_engine(test_url, echo=False)
    expected_checks = {}
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if constraint.name in CONSTRAINT_NAMES:
                expected_checks[constraint.name] = (table.name, str(constraint.sqltext))

    try:
        async with engine.connect() as conn:
            for name in CONSTRAINT_NAMES:
                table_name, expression = expected_checks[name]
                row = (
                    await conn.execute(
                        text(
                            "SELECT contype, pg_get_constraintdef(oid), convalidated "
                            "FROM pg_constraint WHERE conname = :name "
                            "AND conrelid = CAST(:table_name AS regclass)"
                        ),
                        {"name": name, "table_name": table_name},
                    )
                ).first()
                assert row is not None, name
                constraint_type = row[0].decode() if isinstance(row[0], bytes) else row[0]
                assert constraint_type == "c" and row[2] is True, name
                assert _parse_check_expression(row[1]) == _parse_check_expression(
                    f"CHECK ({expression})"
                ), name

            link_columns = (
                ("chitti_transactions", "original_transaction_id"),
                ("chitti_payouts", "ledger_transaction_id"),
            )
            for table_name, column_name in link_columns:
                row = (
                    await conn.execute(
                        text(
                            "SELECT data_type, is_nullable FROM information_schema.columns "
                            "WHERE table_schema = current_schema() "
                            "AND table_name = :table_name AND column_name = :column_name"
                        ),
                        {"table_name": table_name, "column_name": column_name},
                    )
                ).first()
                assert row == ("uuid", "YES")

            foreign_key_specs = (
                ("chitti_transactions", "original_transaction_id"),
                ("chitti_payouts", "ledger_transaction_id"),
            )
            for table_name, column_name in foreign_key_specs:
                definitions = (
                    await conn.execute(
                        text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE contype = 'f' "
                            "AND conrelid = CAST(:table_name AS regclass)"
                        ),
                        {"table_name": table_name},
                    )
                ).scalars().all()
                expected = _normalize_definition(
                    f"FOREIGN KEY ({column_name}) "
                    "REFERENCES chitti_transactions(id) ON DELETE RESTRICT"
                )
                assert any(_normalize_definition(value) == expected for value in definitions)

            unique_specs = (
                ("chitti_transactions", "original_transaction_id"),
                ("chitti_payouts", "ledger_transaction_id"),
            )
            for table_name, column_name in unique_specs:
                definitions = (
                    await conn.execute(
                        text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE contype = 'u' "
                            "AND conrelid = CAST(:table_name AS regclass)"
                        ),
                        {"table_name": table_name},
                    )
                ).scalars().all()
                expected = _normalize_definition(f"UNIQUE ({column_name})")
                assert any(_normalize_definition(value) == expected for value in definitions)

            for index_name, column_name in (
                ("ix_chitti_transaction_original_transaction", "original_transaction_id"),
                ("ix_chitti_payout_ledger_transaction", "ledger_transaction_id"),
            ):
                index_def = await conn.scalar(
                    text(
                        "SELECT indexdef FROM pg_indexes "
                        "WHERE schemaname = current_schema() AND indexname = :index_name"
                    ),
                    {"index_name": index_name},
                )
                assert index_def is not None
                assert column_name in index_def
                assert "UNIQUE" not in index_def.upper()

            lift_columns = (
                await conn.execute(
                    text(
                        "SELECT column_name, data_type, is_nullable "
                        "FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND table_name = 'chitti_lift_events'"
                    )
                )
            ).all()
            assert {
                name: (data_type, nullable)
                for name, data_type, nullable in lift_columns
            } == LIFT_EVENT_COLUMNS
            lift_foreign_keys = (
                await conn.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE contype = 'f' "
                        "AND conrelid = 'chitti_lift_events'::regclass"
                    )
                )
            ).scalars().all()
            expected_lift_foreign_keys = (
                "FOREIGN KEY (chitti_id) REFERENCES chittis(id) ON DELETE CASCADE",
                "FOREIGN KEY (member_id) REFERENCES chitti_members(id) ON DELETE RESTRICT",
                "FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE SET NULL",
                "FOREIGN KEY (reversed_by) REFERENCES users(id) ON DELETE SET NULL",
            )
            normalized_lift_foreign_keys = {
                _normalize_definition(value) for value in lift_foreign_keys
            }
            assert {
                _normalize_definition(value) for value in expected_lift_foreign_keys
            } <= normalized_lift_foreign_keys
            lift_index = await conn.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = current_schema() "
                    "AND indexname = 'uq_chitti_lift_period_active'"
                )
            )
            assert lift_index is not None
            normalized_lift_index = _normalize_definition(lift_index)
            assert normalized_lift_index.endswith("wherereversed_atisnull")
            assert "CREATE UNIQUE INDEX" in lift_index.upper()

            allocation_columns = (
                await conn.execute(
                    text(
                        "SELECT column_name, data_type, is_nullable "
                        "FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND table_name = 'chitti_payment_allocations'"
                    )
                )
            ).all()
            assert {
                name: (data_type, nullable)
                for name, data_type, nullable in allocation_columns
            } == PAYMENT_ALLOCATION_COLUMNS

            allocation_foreign_keys = (
                await conn.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE contype = 'f' "
                        "AND conrelid = 'chitti_payment_allocations'::regclass"
                    )
                )
            ).scalars().all()
            assert {
                _normalize_definition(value) for value in PAYMENT_ALLOCATION_FOREIGN_KEYS
            } <= {
                _normalize_definition(value) for value in allocation_foreign_keys
            }

            allocation_indexes = {
                name: definition
                for name, definition in (
                    await conn.execute(
                        text(
                            "SELECT indexname, indexdef FROM pg_indexes "
                            "WHERE schemaname = current_schema() "
                            "AND tablename = 'chitti_payment_allocations'"
                        )
                    )
                ).all()
            }
            for index_name, columns in (
                ("ix_chitti_payment_allocations_id", ("id",)),
                ("ix_chitti_payment_allocations_source_transaction", ("source_transaction_id",)),
                ("ix_chitti_payment_allocations_member", ("chitti_id", "member_id")),
                ("ix_chitti_payment_allocations_contribution", ("contribution_id",)),
            ):
                assert index_name in allocation_indexes
                assert all(column_name in allocation_indexes[index_name] for column_name in columns)
                assert "UNIQUE" not in allocation_indexes[index_name].upper()

            allocation_enums = {}
            for enum_name, label in (
                await conn.execute(
                    text(
                        "SELECT t.typname, e.enumlabel FROM pg_type t "
                        "JOIN pg_enum e ON e.enumtypid = t.oid "
                        "WHERE t.typname IN "
                        "('chitti_payment_allocation_type_enum', "
                        "'chitti_payment_allocation_event_type_enum') "
                        "ORDER BY t.typname, e.enumsortorder"
                    )
                )
            ).all():
                allocation_enums.setdefault(enum_name, []).append(label)
            assert allocation_enums == {
                "chitti_payment_allocation_type_enum": ["CONTRIBUTION", "CREDIT"],
                "chitti_payment_allocation_event_type_enum": [
                    "PAYMENT", "REVERSAL", "CREDIT_UTILIZATION", "LIFT_ADJUSTMENT",
                ],
            }
    finally:
        await engine.dispose()


LIFT_EVENT_COLUMNS = {
    "id": ("uuid", "NO"),
    "chitti_id": ("uuid", "NO"),
    "member_id": ("uuid", "NO"),
    "period_number": ("integer", "NO"),
    "lift_date": ("date", "NO"),
    "recorded_by": ("uuid", "YES"),
    "reversed_at": ("timestamp with time zone", "YES"),
    "reversed_by": ("uuid", "YES"),
    "reversal_reason": ("text", "YES"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
}

PAYMENT_ALLOCATION_COLUMNS = {
    "id": ("uuid", "NO"),
    "chitti_id": ("uuid", "NO"),
    "member_id": ("uuid", "NO"),
    "source_transaction_id": ("uuid", "NO"),
    "event_transaction_id": ("uuid", "YES"),
    "contribution_id": ("uuid", "YES"),
    "allocation_type": ("USER-DEFINED", "NO"),
    "event_type": ("USER-DEFINED", "NO"),
    "amount": ("numeric", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "updated_at": ("timestamp with time zone", "NO"),
}

PAYMENT_ALLOCATION_FOREIGN_KEYS = (
    "FOREIGN KEY (chitti_id) REFERENCES chittis(id) ON DELETE CASCADE",
    "FOREIGN KEY (member_id) REFERENCES chitti_members(id) ON DELETE RESTRICT",
    "FOREIGN KEY (source_transaction_id) REFERENCES chitti_transactions(id) ON DELETE RESTRICT",
    "FOREIGN KEY (event_transaction_id) REFERENCES chitti_transactions(id) ON DELETE RESTRICT",
    "FOREIGN KEY (contribution_id) REFERENCES chitti_member_contributions(id) ON DELETE RESTRICT",
)


async def _create_linked_financial_test_records(test_url):
    engine = create_async_engine(test_url, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            chitti, member = await _make_chitti_fixture(session)
            original = ChittiTransaction(
                chitti_id=chitti.id,
                member_id=member.id,
                transaction_type="CONTRIBUTION",
                amount=Decimal("100"),
                payment_method="CASH",
                period_number=1,
                idempotency_key=f"migration-origin-{uuid.uuid4()}",
            )
            payout_ledger = ChittiTransaction(
                chitti_id=chitti.id,
                member_id=member.id,
                transaction_type="PAYOUT",
                amount=Decimal("100"),
                payment_method="CASH",
                period_number=1,
                idempotency_key=f"migration-payout-{uuid.uuid4()}",
            )
            session.add_all((original, payout_ledger))
            await session.flush()
            reversal = ChittiTransaction(
                chitti_id=chitti.id,
                member_id=member.id,
                transaction_type="REVERSAL",
                amount=Decimal("100"),
                payment_method="CASH",
                period_number=1,
                original_transaction_id=original.id,
                idempotency_key=f"migration-reversal-{uuid.uuid4()}",
            )
            payout = ChittiPayout(
                chitti_id=chitti.id,
                member_id=member.id,
                period_number=1,
                ledger_transaction_id=payout_ledger.id,
                gross_payout=Decimal("100"),
                discount_amount=Decimal("0"),
                fee_amount=Decimal("0"),
                net_payout=Decimal("100"),
                payout_method="CASH",
                status="PAID",
            )
            lift = ChittiLiftEvent(
                chitti_id=chitti.id,
                member_id=member.id,
                period_number=1,
                lift_date=date.today(),
            )
            allocation = ChittiPaymentAllocation(
                chitti_id=chitti.id,
                member_id=member.id,
                source_transaction_id=original.id,
                allocation_type="CREDIT",
                event_type="PAYMENT",
                amount=Decimal("1"),
            )
            session.add_all((reversal, payout, lift, allocation))
            await session.commit()
            return reversal.id, payout.id, lift.id, allocation.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_migrations_upgrade_downgrade_reupgrade_from_older_schema():
    test_url, config = await _prepare_migration_schema()
    try:
        await _run_migration(command.upgrade, config, "head")
        await _assert_financial_migration_schema(test_url)

        reversal_id, payout_id, lift_id, allocation_id = await _create_linked_financial_test_records(test_url)
        with pytest.raises(RuntimeError, match="payment allocation history exists"):
            await _run_migration(command.downgrade, config, "0004_chitti_financial_links")

        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM chitti_payment_allocations WHERE id = :id"),
                    {"id": allocation_id},
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="financial link values exist"):
            await _run_migration(command.downgrade, config, "0003_chitti_financial_checks")

        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                reversal_link = await conn.scalar(
                    text(
                        "SELECT original_transaction_id FROM chitti_transactions "
                        "WHERE id = :id"
                    ),
                    {"id": reversal_id},
                )
                payout_link = await conn.scalar(
                    text(
                        "SELECT ledger_transaction_id FROM chitti_payouts WHERE id = :id"
                    ),
                    {"id": payout_id},
                )
                assert reversal_link is not None
                assert payout_link is not None
                await conn.execute(
                    text(
                        "UPDATE chitti_transactions SET original_transaction_id = NULL "
                        "WHERE id = :id"
                    ),
                    {"id": reversal_id},
                )
                await conn.execute(
                    text(
                        "UPDATE chitti_payouts SET ledger_transaction_id = NULL "
                        "WHERE id = :id"
                    ),
                    {"id": payout_id},
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="chitti_lift_events contains lift history"):
            await _run_migration(command.downgrade, config, "0001_baseline")

        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM chitti_lift_events WHERE id = :id"),
                    {"id": lift_id},
                )
        finally:
            await engine.dispose()

        await _run_migration(command.downgrade, config, "0002_lift_events")
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.connect() as conn:
                assert await conn.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND ((table_name = 'chitti_transactions' "
                        "AND column_name = 'original_transaction_id') "
                        "OR (table_name = 'chitti_payouts' "
                        "AND column_name = 'ledger_transaction_id'))"
                    )
                ) == 0
                remaining_checks = (
                    await conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE contype = 'c' AND conname LIKE 'ck_chitti_%'"
                        )
                    )
                ).scalars().all()
                assert not set(remaining_checks).intersection(CONSTRAINT_NAMES)
                assert await conn.scalar(
                    text(
                        "SELECT to_regclass('chitti_lift_events') IS NOT NULL"
                    )
                )
        finally:
            await engine.dispose()

        await _run_migration(command.upgrade, config, "head")
        await _assert_financial_migration_schema(test_url)
        await _run_migration(command.downgrade, config, "0001_baseline")
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.connect() as conn:
                assert await conn.scalar(
                    text("SELECT to_regclass('chitti_lift_events') IS NULL")
                )
        finally:
            await engine.dispose()
        await _run_migration(command.upgrade, config, "head")
        await _assert_financial_migration_schema(test_url)
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_fresh_install_migrations_validate_baseline_objects():
    from tests.conftest import _assert_scratch_database

    _assert_scratch_database()
    test_url = os.environ["TEST_DATABASE_URL"]
    await _reset_migration_schema(test_url)
    config = _migration_config(test_url)
    try:
        await _run_migration(command.upgrade, config, "head")
        await _assert_financial_migration_schema(test_url)
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_valid_preexisting_lift_table_is_validated_and_preserved():
    test_url, config = await _prepare_migration_schema(include_lift_events=True)
    try:
        await _run_migration(command.upgrade, config, "head")
        await _assert_financial_migration_schema(test_url)
        await _run_migration(command.downgrade, config, "0001_baseline")
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.connect() as conn:
                assert await conn.scalar(
                    text("SELECT to_regclass('chitti_lift_events') IS NOT NULL")
                )
                comment = await conn.scalar(
                    text(
                        "SELECT obj_description('chitti_lift_events'::regclass, 'pg_class')"
                    )
                )
                assert comment is None
        finally:
            await engine.dispose()
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_migration_rejects_incompatible_preexisting_lift_index():
    test_url, config = await _prepare_migration_schema(include_lift_events=True)
    try:
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql("DROP INDEX uq_chitti_lift_period_active")
                await conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX uq_chitti_lift_period_active "
                    "ON chitti_lift_events (chitti_id, period_number)"
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="index uq_chitti_lift_period_active is incompatible"):
            await _run_migration(command.upgrade, config, "head")
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_migration_rejects_preexisting_lift_table_missing_columns():
    test_url, config = await _prepare_migration_schema()
    try:
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "CREATE TABLE chitti_lift_events (id UUID PRIMARY KEY)"
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="missing required columns"):
            await _run_migration(command.upgrade, config, "head")
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_migration_rejects_incompatible_preexisting_lift_column_type():
    test_url, config = await _prepare_migration_schema(include_lift_events=True)
    try:
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_lift_events "
                    "ALTER COLUMN period_number TYPE BIGINT"
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="chitti_lift_events.period_number is incompatible"):
            await _run_migration(command.upgrade, config, "head")
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_migration_rejects_incompatible_preexisting_lift_foreign_key():
    test_url, config = await _prepare_migration_schema(include_lift_events=True)
    try:
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_lift_events "
                    "DROP CONSTRAINT chitti_lift_events_member_id_fkey"
                )
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_lift_events "
                    "ADD CONSTRAINT chitti_lift_events_member_id_fkey "
                    "FOREIGN KEY (member_id) REFERENCES chitti_members(id) "
                    "ON DELETE CASCADE"
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="foreign key for member_id is incompatible"):
            await _run_migration(command.upgrade, config, "head")
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_migration_rejects_wrong_existing_financial_check_definition():
    test_url, config = await _prepare_migration_schema()
    try:
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_member_contributions "
                    "ADD CONSTRAINT ck_chitti_contribution_expected_amount_nonnegative "
                    "CHECK (expected_amount <= 0)"
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="incompatible definition"):
            await _run_migration(command.upgrade, config, "head")
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_migration_rejects_incompatible_existing_link_column():
    test_url, config = await _prepare_migration_schema()
    try:
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_transactions "
                    "ADD COLUMN original_transaction_id BIGINT"
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="must be a nullable UUID"):
            await _run_migration(command.upgrade, config, "head")
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_migration_rejects_wrong_existing_link_foreign_key():
    test_url, config = await _prepare_migration_schema()
    try:
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_transactions "
                    "ADD COLUMN original_transaction_id UUID"
                )
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_transactions "
                    "ADD CONSTRAINT fk_chitti_transaction_original_transaction "
                    "FOREIGN KEY (original_transaction_id) REFERENCES users(id) "
                    "ON DELETE RESTRICT"
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="foreign key chitti_transactions"):
            await _run_migration(command.upgrade, config, "head")
    finally:
        await _reset_migration_schema(test_url)


@pytest.mark.asyncio
async def test_migration_rejects_wrong_existing_link_unique_definition():
    test_url, config = await _prepare_migration_schema()
    try:
        engine = create_async_engine(test_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_transactions "
                    "ADD COLUMN original_transaction_id UUID"
                )
                await conn.exec_driver_sql(
                    "ALTER TABLE chitti_transactions "
                    "ADD CONSTRAINT uq_chitti_transaction_original UNIQUE (chitti_id)"
                )
        finally:
            await engine.dispose()

        with pytest.raises(RuntimeError, match="unique constraint chitti_transactions"):
            await _run_migration(command.upgrade, config, "head")
    finally:
        await _reset_migration_schema(test_url)
