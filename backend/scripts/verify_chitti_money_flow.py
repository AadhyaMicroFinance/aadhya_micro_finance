"""End-to-end money-flow verification for Chitti.

Enrolls a member through the real agreement workflow, starts the chitti, records a
back-dated partial payment followed by the remainder, retries the first request with
the same idempotency key, then asserts that the ledger, schedules, member totals and
analytics all agree. Cleans up the test chitti at the end.

Run inside the backend container:
    PYTHONPATH=/app python scripts/verify_chitti_money_flow.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg2

API = os.environ.get("VERIFY_API_BASE", "http://localhost:8000/api/v1")
DB_URL = os.environ["DATABASE_URL_SYNC"]
IST = ZoneInfo("Asia/Kolkata")

failures: list[str] = []
checks = 0


def check(label: str, actual, expected) -> None:
    global checks
    checks += 1
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")
        print(f"FAIL  {label}: expected {expected!r}, got {actual!r}")
    else:
        print(f"ok    {label} = {actual!r}")


def request(method: str, path: str, payload=None, token=None):
    url = f"{API}{path}"
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return exc.code, {"raw": body}


def login() -> str:
    status, body = request(
        "POST", "/auth/login", {"username": "admin", "password": "admin123"}
    )
    if status != 200:
        raise SystemExit(f"login failed: {status} {body}")
    return body["data"]["access_token"] if "data" in body else body["access_token"]


def main() -> int:
    token = login()
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT CURRENT_DATE, now() AT TIME ZONE 'Asia/Kolkata'")
    today = cur.fetchone()[1].date()
    yesterday = today - timedelta(days=1)
    start_date = today - timedelta(days=14)  # periods 1 and 2 already due

    cur.execute("SELECT id FROM chitti_plans WHERE plan_code = 'PLN-000001'")
    plan_id = cur.fetchone()[0]
    cur.execute("SELECT id FROM customers ORDER BY created_at LIMIT 1")
    customer_id = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(amount),0) FROM chitti_transactions")
    baseline_ledger = Decimal(str(cur.fetchone()[0]))

    chitti_id = None
    try:
        # ---------------------------------------------------------------- create
        status, body = request(
            "POST",
            "/chitti/",
            {
                "plan_id": str(plan_id),
                "name": "[TEST] Money Flow Verification",
                "start_date": str(start_date),
                "member_count": 1,
            },
            token,
        )
        check("create chitti status", status, 200)
        chitti_id = body["data"]["id"]

        # ---------------------------------------------------- agreement workflow
        status, body = request(
            "POST",
            f"/chitti/{chitti_id}/members",
            {"customer_id": str(customer_id)},
            token,
        )
        check("add member (PENDING_AGREEMENT)", status, 200)
        member_id = body["data"]["id"]
        check("member status after add", body["data"]["status"], "PENDING_AGREEMENT")

        for action, expected_status in (
            ("generate", "AGREEMENT_GENERATED"),
            ("print", "AGREEMENT_PRINTED"),
            ("confirm", "ACTIVE"),
        ):
            status, body = request(
                "POST",
                f"/chitti/{chitti_id}/members/{member_id}/agreement/{action}",
                {},
                token,
            )
            if status == 422:  # endpoint may take no body
                status, body = request(
                    "POST",
                    f"/chitti/{chitti_id}/members/{member_id}/agreement/{action}",
                    None,
                    token,
                )
            check(f"agreement {action} status", status, 200)

        status, body = request(
            "GET", f"/chitti/{chitti_id}/members", None, token
        )
        check("member status after confirm", body["data"][0]["status"], "ACTIVE")

        # Contributions must exist the moment the member is activated.
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_amount),0) "
            "FROM chitti_member_contributions WHERE member_id = %s",
            (member_id,),
        )
        contribution_count, contribution_expected = cur.fetchone()
        check("contributions generated on activation", contribution_count, 25)
        check(
            "member expected total from schedule",
            Decimal(str(contribution_expected)),
            Decimal("50000"),
        )

        cur.execute(
            "SELECT total_expected_amount FROM chitti_members WHERE id = %s",
            (member_id,),
        )
        check(
            "member.total_expected_amount",
            Decimal(str(cur.fetchone()[0])),
            Decimal("50000"),
        )

        # --------------------------------------------------------------- start
        status, body = request("POST", f"/chitti/{chitti_id}/start", {}, token)
        if status == 422:
            status, body = request("POST", f"/chitti/{chitti_id}/start", None, token)
        check("start chitti status", status, 200)
        check("chitti status", body["data"]["status"], "RUNNING")

        # ------------------------------------------------- partial, back-dated
        key1 = f"verify-{uuid.uuid4()}"
        payment1 = {
            "member_id": str(member_id),
            "period_number": 1,
            "amount": 1200,
            "payment_method": "CASH",
            "payment_date": str(yesterday),
            "idempotency_key": key1,
        }
        status, body = request(
            "POST", f"/chitti/{chitti_id}/contributions", payment1, token
        )
        check("partial payment status", status, 200)
        check("partial payment state", body["data"]["status"], "PARTIALLY_PAID")
        check("partial remaining", Decimal(str(body["data"]["remaining_amount"])), Decimal("800.00"))

        # ------------------------------------------------------ idempotent retry
        status, body = request(
            "POST", f"/chitti/{chitti_id}/contributions", payment1, token
        )
        check("retry status", status, 200)
        check("retry flagged duplicate", body["data"].get("duplicate"), True)
        cur.execute(
            "SELECT COUNT(*) FROM chitti_transactions WHERE idempotency_key = %s",
            (key1,),
        )
        check("retry created no extra ledger row", cur.fetchone()[0], 1)

        # --------------------------------------------------------- final payment
        key2 = f"verify-{uuid.uuid4()}"
        status, body = request(
            "POST",
            f"/chitti/{chitti_id}/contributions",
            {
                "member_id": str(member_id),
                "period_number": 1,
                "amount": 800,
                "payment_method": "UPI",
                "payment_date": str(today),
                "idempotency_key": key2,
            },
            token,
        )
        check("final payment status", status, 200)
        check("final payment state", body["data"]["status"], "PAID")
        check("final remaining", Decimal(str(body["data"]["remaining_amount"])), Decimal("0.00"))

        # ------------------------------------------------------- DB invariants
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM chitti_transactions "
            "WHERE chitti_id = %s AND transaction_type = 'CONTRIBUTION'",
            (chitti_id,),
        )
        txn_count, txn_total = cur.fetchone()
        check("ledger rows for chitti", txn_count, 2)
        check("ledger contribution total", Decimal(str(txn_total)), Decimal("2000"))

        cur.execute(
            "SELECT COALESCE(SUM(actual_collection),0), COALESCE(SUM(pending_collection),0) "
            "FROM chitti_period_schedule WHERE chitti_id = %s",
            (chitti_id,),
        )
        sched_actual, sched_pending = cur.fetchone()
        check("schedule actual", Decimal(str(sched_actual)), Decimal("2000"))
        check("schedule pending", Decimal(str(sched_pending)), Decimal("48000"))

        cur.execute(
            "SELECT COALESCE(SUM(paid_amount),0), COALESCE(SUM(remaining_amount),0) "
            "FROM chitti_member_contributions WHERE chitti_id = %s",
            (chitti_id,),
        )
        contrib_paid, contrib_remaining = cur.fetchone()
        check("contributions paid", Decimal(str(contrib_paid)), Decimal("2000"))
        check("contributions remaining", Decimal(str(contrib_remaining)), Decimal("48000"))

        cur.execute(
            "SELECT total_expected_amount, total_paid_amount, outstanding_amount "
            "FROM chitti_members WHERE id = %s",
            (member_id,),
        )
        m_expected, m_paid, m_outstanding = cur.fetchone()
        check("member paid", Decimal(str(m_paid)), Decimal("2000"))
        check("member outstanding", Decimal(str(m_outstanding)), Decimal("48000"))

        cur.execute(
            "SELECT payment_date FROM chitti_transactions WHERE chitti_id = %s "
            "ORDER BY payment_date",
            (chitti_id,),
        )
        dates = [r[0] for r in cur.fetchall()]
        check("ledger business dates", dates, [yesterday, today])

        # ----------------------------------------------------- analytics agrees
        status, body = request(
            "GET", f"/analytics/chitti/overview?chitti_id={chitti_id}", None, token
        )
        check("analytics status", status, 200)
        data = body["data"]
        check("analytics collected", Decimal(str(data["kpis"]["total_collected"])), Decimal("2000"))
        check("analytics pending", Decimal(str(data["kpis"]["total_pending"])), Decimal("48000"))
        check("analytics overdue", Decimal(str(data["kpis"]["total_overdue"])), Decimal("2000"))
        check("analytics today collected", Decimal(str(data["today"]["collected"])), Decimal("800"))
        check("analytics today expected", Decimal(str(data["today"]["expected"])), Decimal("2000"))
        check(
            "analytics collection efficiency",
            Decimal(str(data["kpis"]["collection_efficiency"])),
            Decimal("4.0"),
        )

        series = {row["date"]: row for row in data["daily"]["series"]}
        check(
            "back-dated payment reported yesterday",
            Decimal(str(series[str(yesterday)]["collected"])),
            Decimal("1200"),
        )
        check(
            "today payment reported today",
            Decimal(str(series[str(today)]["collected"])),
            Decimal("800"),
        )

        row = data["member_rows"][0]
        check("member analytics paid", Decimal(str(row["paid_total"])), Decimal("2000"))
        check("member analytics due pending", Decimal(str(row["due_pending"])), Decimal("4000"))
        check("member analytics status", row["status"], "OVERDUE")

        metric = data["chitti_metrics"][0]
        check("chitti metric collected", Decimal(str(metric["collected"])), Decimal("2000"))
        check("chitti metric pending", Decimal(str(metric["pending"])), Decimal("48000"))
        check("chitti metric overdue", Decimal(str(metric["overdue"])), Decimal("2000"))

        status, body = request(
            "GET", f"/analytics/chitti/transactions?chitti_id={chitti_id}", None, token
        )
        check("ledger endpoint rows", len(body["data"]), 2)
        check(
            "ledger endpoint business dates",
            sorted(r["payment_date"] for r in body["data"]),
            [str(yesterday), str(today)],
        )
    finally:
        if chitti_id:
            cur.execute("DELETE FROM chittis WHERE id = %s", (chitti_id,))
            cur.execute(
                "SELECT (SELECT COUNT(*) FROM chitti_members WHERE chitti_id = %s) + "
                "(SELECT COUNT(*) FROM chitti_member_contributions WHERE chitti_id = %s) + "
                "(SELECT COUNT(*) FROM chitti_transactions WHERE chitti_id = %s) + "
                "(SELECT COUNT(*) FROM chitti_agreements WHERE chitti_id = %s) + "
                "(SELECT COUNT(*) FROM chitti_period_schedule WHERE chitti_id = %s)",
                (chitti_id,) * 5,
            )
            check("cascade cleanup left no child rows", cur.fetchone()[0], 0)

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM chitti_transactions")
        check(
            "ledger restored after cleanup",
            Decimal(str(cur.fetchone()[0])),
            baseline_ledger,
        )
        cur.close()
        conn.close()

    print(f"\n{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("ALL MONEY-FLOW CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
