"""
Customer model — full onboarding fields.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Customer(BaseModel):
    """Customer master record — registered before joining any chitti."""

    __tablename__ = "customers"

    # --- Identity ---
    customer_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(
        Enum("MALE", "FEMALE", "OTHER", name="gender_enum"), nullable=True
    )

    # --- Contact ---
    mobile_number: Mapped[str] = mapped_column(String(20), nullable=False)
    alternate_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Address ---
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # --- KYC ---
    pan_number: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    aadhar_number: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)

    # --- Other ---
    occupation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nominee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nominee_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nominee_relation: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Meta ---
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "INACTIVE", "BLOCKED", name="customer_status_enum"),
        default="ACTIVE",
        nullable=False,
    )

    # Relationships
    finance_accounts: Mapped[list["FinanceAccount"]] = relationship(
        "FinanceAccount",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    chitti_memberships: Mapped[list["ChittiMember"]] = relationship(
        "ChittiMember",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    payments: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction",
        back_populates="customer",
    )
    whatsapp_messages: Mapped[list["WhatsAppMessageLog"]] = relationship(
        "WhatsAppMessageLog",
        back_populates="customer",
    )
