"""
Report schemas.
"""

from decimal import Decimal
from pydantic import BaseModel
from typing import Optional
from datetime import date


class DateRangeParams(BaseModel):
    start_date: date
    end_date: date


class DailyCollectionReport(BaseModel):
    date: date
    total_collected: Decimal
    total_expected: Decimal
    collection_count: int
    finance_collected: Decimal
    chitti_collected: Decimal
    cash_amount: Decimal
    upi_amount: Decimal
    bank_transfer_amount: Decimal
    other_amount: Decimal


class OutstandingReport(BaseModel):
    customer_id: str
    customer_name: str
    customer_code: str
    account_type: str
    account_number: str
    total_payable: Decimal
    total_paid: Decimal
    outstanding: Decimal
    overdue_amount: Decimal
    last_payment_date: Optional[date] = None


class OverdueReport(BaseModel):
    customer_id: str
    customer_name: str
    customer_code: str
    mobile_number: str
    account_number: str
    overdue_installments: int
    overdue_amount: Decimal
    oldest_overdue_date: date


class CollectorReport(BaseModel):
    collector_id: str
    collector_name: str
    total_collected: Decimal
    payment_count: int
    finance_amount: Decimal
    chitti_amount: Decimal
