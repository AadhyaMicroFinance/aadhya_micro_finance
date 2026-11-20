from decimal import Decimal
from uuid import UUID

from app.services.chitti_calculation import ChittiCalculationEngine


ZERO = Decimal("0")


def lift_periods_by_member(lifts):
    result: dict[UUID, int] = {}
    for event in lifts:
        if getattr(event, "reversed_at", None) is not None:
            continue
        prior = result.get(event.member_id)
        result[event.member_id] = (
            min(prior, event.period_number) if prior is not None
            else event.period_number
        )
    return result


def effective_contribution_values(chitti, members, lifts, contributions):
    member_by_id = {member.id: member for member in members}
    lift_by_member = lift_periods_by_member(lifts)
    snapshot = chitti.plan_snapshot or {}
    engine = ChittiCalculationEngine(snapshot)
    duration = int(snapshot.get("duration", 0))
    total_value = Decimal(str(snapshot.get("total_value", 0)))
    member_count = int(snapshot.get("member_count", chitti.member_count))

    result = {}
    for row in contributions:
        member = member_by_id.get(row.member_id)
        expected = row.expected_amount
        if member and hasattr(engine.contribution_strategy, "calculate_installment_for_member"):
            expected = engine.contribution_strategy.calculate_installment_for_member(
                row.period_number,
                duration,
                total_value,
                member_count,
                lift_by_member.get(member.id),
            )
        paid = Decimal(str(row.paid_amount or ZERO))
        remaining = max(expected - paid, ZERO)
        result[row.id] = {
            "expected": expected,
            "paid": paid,
            "remaining": remaining,
        }
    return result


def aggregate_period_values(schedules, contributions, contribution_values):
    """Aggregate member values by period, falling back only for legacy periods."""
    totals = {}
    for contribution in contributions:
        key = (contribution.chitti_id, contribution.period_number)
        values = totals.setdefault(
            key,
            {"expected": ZERO, "paid": ZERO, "pending": ZERO},
        )
        effective = contribution_values[contribution.id]
        values["expected"] += effective["expected"]
        values["paid"] += effective["paid"]
        values["pending"] += effective["remaining"]

    result = dict(totals)
    for schedule in schedules:
        key = (schedule.chitti_id, schedule.period_number)
        if key in totals:
            result[key] = totals[key]
        else:
            expected = Decimal(str(schedule.expected_collection or ZERO))
            paid = Decimal(str(schedule.actual_collection or ZERO))
            result[key] = {
                "expected": expected,
                "paid": paid,
                "pending": max(expected - paid, ZERO),
            }
    return result


def unallocated_credit_by_member(allocations):
    credits = {}
    for allocation in allocations:
        if allocation.allocation_type != "CREDIT":
            continue
        credits[allocation.member_id] = (
            credits.get(allocation.member_id, ZERO)
            + Decimal(str(allocation.amount))
        )
    invalid = {member_id: amount for member_id, amount in credits.items() if amount < ZERO}
    if invalid:
        raise ValueError("Chitti payment allocation history contains negative member credit.")
    return {member_id: amount for member_id, amount in credits.items() if amount > ZERO}
