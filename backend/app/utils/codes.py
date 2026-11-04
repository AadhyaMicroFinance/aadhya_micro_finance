"""
Auto-generated sequential codes for entities.

Examples:
    CUS-000001
    FIN-000001
    PLN-000001
    CHIT-000001
    PAY-20260819-000001
"""

from datetime import date
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.customer import Customer
from app.models.finance import FinanceAccount
from app.models.chitti import ChittiPlan, Chitti
from app.models.payment import PaymentTransaction

settings = get_settings()


async def _get_next_number(session: AsyncSession, model, code_column) -> int:
    """Get the next sequential number for a code prefix."""
    result = await session.execute(
        select(func.count()).select_from(model)
    )
    count = result.scalar()
    return (count or 0) + 1


async def generate_customer_code(session: AsyncSession) -> str:
    """Generate customer code: CUS-000001"""
    number = await _get_next_number(session, Customer, Customer.customer_code)
    return f"{settings.CUSTOMER_CODE_PREFIX}-{number:06d}"


async def generate_finance_code(session: AsyncSession) -> str:
    """Generate finance account number: FIN-000001"""
    number = await _get_next_number(session, FinanceAccount, FinanceAccount.account_number)
    return f"{settings.FINANCE_CODE_PREFIX}-{number:06d}"


async def generate_plan_code(session: AsyncSession) -> str:
    """Generate chitti plan code: PLN-000001"""
    number = await _get_next_number(session, ChittiPlan, ChittiPlan.plan_code)
    return f"PLN-{number:06d}"


async def generate_chitti_code(session: AsyncSession) -> str:
    """Generate chitti instance code: CHIT-000001"""
    number = await _get_next_number(session, Chitti, Chitti.chitti_code)
    return f"{settings.CHITTI_CODE_PREFIX}-{number:06d}"


async def generate_payment_id(session: AsyncSession) -> str:
    """Generate payment transaction ID: PAY-20260819-000001"""
    today = date.today().strftime("%Y%m%d")
    # Count payments created today
    result = await session.execute(
        select(func.count()).select_from(PaymentTransaction)
        .where(
            PaymentTransaction.transaction_id.like(f"{settings.PAYMENT_CODE_PREFIX}-{today}-%")
        )
    )
    count = result.scalar()
    number = (count or 0) + 1
    return f"{settings.PAYMENT_CODE_PREFIX}-{today}-{number:06d}"
