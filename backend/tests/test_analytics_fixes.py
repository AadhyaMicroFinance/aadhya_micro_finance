"""Analytics regressions: advance cash, date windows and ledger IDs."""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.analytics_service import ChittiAnalyticsService


def test_advance_amount_counts_future_receipt_once():
    chitti_id = uuid4()
    row = {
        "contribution": SimpleNamespace(
            chitti_id=chitti_id,
            period_number=1,
            paid_amount=Decimal("3500"),
        ),
        "effective": {"paid": Decimal("3500"), "expected": Decimal("1000")},
    }
    today = date(2026, 11, 21)

    future = SimpleNamespace(due_date=date(2026, 12, 1))
    assert ChittiAnalyticsService._advance_amount(
        row, {(chitti_id, 1): future}, today
    ) == Decimal("3500")

    due = SimpleNamespace(due_date=date(2026, 11, 1))
    assert ChittiAnalyticsService._advance_amount(
        row, {(chitti_id, 1): due}, today
    ) == Decimal("2500")


def test_daily_series_covers_full_requested_range():
    service = ChittiAnalyticsService(None)
    start = date(2026, 1, 1)
    end = date(2026, 5, 1)
    series = service._daily_series([], [], start, end, date(2026, 5, 1), {})

    assert series[0]["date"] == str(start)
    assert series[-1]["date"] == str(end)
    assert len(series) == (end - start).days + 1


def test_empty_overview_keeps_requested_filters():
    chitti_id = uuid4()
    data = ChittiAnalyticsService(None)._empty_overview(
        date(2026, 11, 1),
        date(2026, 11, 30),
        chitti_id=chitti_id,
        payment_mode="UPI",
        status="OVERDUE",
    )
    assert data["filters"]["chitti_id"] == str(chitti_id)
    assert data["filters"]["payment_mode"] == "UPI"
    assert data["filters"]["status"] == "OVERDUE"


def test_analytics_transaction_id_uses_full_uuid():
    transaction_id = uuid4()
    txn = SimpleNamespace(
        id=transaction_id,
        member_id=None,
        chitti_id=uuid4(),
        transaction_type="CONTRIBUTION",
        amount=Decimal("500"),
        payment_method="CASH",
        reference_number=None,
        period_number=1,
        created_at=datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc),
        created_by=None,
        payment_date=date(2026, 11, 21),
        notes=None,
    )
    rows = ChittiAnalyticsService(None)._build_transactions(
        [txn], {}, {}, {}, {}
    )
    assert rows[0]["transaction_id"] == f"CTX-{str(transaction_id).upper()}"
