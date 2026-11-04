"""
SQLAlchemy models.
Import all models here so Alembic can detect them.
"""

from app.models.base import BaseModel  # noqa: F401
from app.models.user import User, Role, UserRole  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.finance import FinanceAccount, FinanceSchedule  # noqa: F401
from app.models.chitti import (  # noqa: F401
    ChittiPlan,
    Chitti,
    ChittiMember,
    ChittiAgreement,
    ChittiPeriodSchedule,
    ChittiMemberContribution,
    ChittiPayout,
    ChittiTransaction,
)
from app.models.payment import PaymentTransaction  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.whatsapp import WhatsAppMessageLog  # noqa: F401
from app.models.settings import AppSettings  # noqa: F401
