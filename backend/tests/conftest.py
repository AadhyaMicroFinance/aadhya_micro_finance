"""
Pytest configuration and shared fixtures.
"""

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.db.database import Base, get_db
from app.main import app
from app.core.security import hash_password, create_access_token


# Test database URL (use a separate test database)
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_chitti_test"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    """Create a test database session."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(test_engine, db_session):
    """Create async test client."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user and return tokens."""
    from app.models.user import User

    user = User(
        id=uuid.uuid4(),
        username="testadmin",
        email="admin@test.com",
        password_hash=hash_password("testpass123"),
        full_name="Test Admin",
        role="ADMIN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role}
    )
    return {"user": user, "token": access_token}


@pytest_asyncio.fixture
async def test_customer(db_session, test_user):
    """Create a test customer."""
    from app.models.customer import Customer

    customer = Customer(
        id=uuid.uuid4(),
        customer_code="CUS-000001",
        full_name="Sravan Kumar",
        mobile_number="9876543210",
        address="Hyderabad, Telangana",
        status="ACTIVE",
    )
    db_session.add(customer)
    await db_session.flush()
    return customer
