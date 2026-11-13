# Aadhya Chitti Management — Bug Fix & QA Report

Date: 2026-11-09
Scope: BUG-001 … BUG-004, IMP-001 … IMP-005, IMP-007 (no financial formulae changed)
Application: `finance-chitti-system` (FastAPI + Next.js + PostgreSQL)

---

## 0. Data preservation statement

No demo/test record was deleted, edited or regenerated. No table was dropped,
truncated or recreated in the development database. **No database migration was
required** — every fix lives in application code, and all schema changes are
avoided entirely.

Existing data observed before changes (development database `finance_chitti`):

| Entity | Count / detail |
|---|---|
| customers | 4 |
| chitti_plans | 3 |
| chittis | 3 (`CHIT-000001` DRAFT 3/25, `DEMO-0001` RUNNING 4/4, `DEMO-0002` RUNNING 3/3) |
| chitti_members | 10 (all `ACTIVE`) |
| chitti_member_contributions | present for the two RUNNING demo chittis |
| chitti_period_schedule | 25 periods per chitti |
| payment_transactions | present (ledger untouched) |

Record counts after all work: **identical**. Verified by re-querying the same
aggregates after the test run.

Backups: the deployed stack has a `pg_dump`-based backup script
(`deploy/aws/backup.sh`). See §9 for the scheduling caveat on the EC2 host.

> Note on the reported reproduction: the development database currently has all
> members in `ACTIVE` state, so the "10 members but dashboard shows 0" symptom
> was reproduced on an isolated scratch database (`finance_chitti_test`) using
> the real enrollment flow, rather than by modifying demo rows.

---

## 1. BUG-001 — Incorrect member count on the Chitti dashboard

**Status: FIXED AND TESTED**

### Confirmed root cause
Three different definitions of "member count" were in use:

1. `ChittiService.get_dashboard()` returned `member_count = count_active()`,
   and `count_active()` counts **only** rows with `status = 'ACTIVE'`.
   Members enrolled through the agreement workflow are `PENDING_AGREEMENT` until
   their agreement is confirmed, so a chitti with 10 enrolled members reported
   **0** on the dashboard.
2. `ChittiService.get_summary()` returned `member_count` = plan **capacity**
   (e.g. 10) and `active_members` = ACTIVE-only, with no field for enrolled.
3. The detail page computed `currentMemberCount = members.length || summary.active_members`,
   so the overview tab (where the member list had not been loaded) fell back to
   `active_members` = 0 while the Members tab (which loads the list) showed 10.

### Evidence (before)
`GET /api/v1/chitti/dashboard` on `CHIT-000001` (3 enrolled, 0 pending
agreements in demo data) returned `member_count` equal to the ACTIVE count only;
for a chitti with pending-agreement members it returns 0 while
`GET /api/v1/chitti/{id}/members` returns the full list.

### Fix
- `app/repositories/chitti_repo.py`: added `count_enrolled()` (all statuses
  except `CANCELLED`/`REJECTED`) and `count_pending_agreements()`.
- `app/services/chitti_service.py`:
  `get_dashboard()` → `member_count` **is** the enrolled count, plus explicit
  `enrolled_members`, `active_members`, `member_capacity`.
  `get_summary()` → adds `enrolled_members`, `member_capacity`; `member_count`
  remains the capacity for backwards compatibility.
- `web/src/app/chitti/[id]/page.tsx`: member count everywhere comes from
  `summary.enrolled_members`; the member list is loaded with the page (no more
  `0` fallback on the overview tab); capacity comes from `member_capacity`.
- `web/src/app/chitti/page.tsx`: cards show `enrolled / capacity`.

### Verified
- Dashboard `member_count` == summary `enrolled_members` == members list length
  == 10 (automated test `test_member_count_duplicate_and_activation`).
- Live API on demo data: `DEMO-0001` → `members=4/4 active=4`;
  `DEMO-0002` → `3/3 active=3`; `CHIT-000001` → `3/25 active=3`.

---

## 2. BUG-002 — Duplicate member shows a generic HTTP error

**Status: FIXED AND TESTED**

### Confirmed root cause
The backend already returned `409` with a message, but:
- `web/src/services/api-client.ts` had no error-message extraction, so the dialog
  rendered axios' `Request failed with status code 409`;
- the error body did not carry a stable code or the conflicting member, so the UI
  could not distinguish "already enrolled" from "chitti full";
- additionally, re-adding a previously `CANCELLED`/`REJECTED` customer would have
  hit the `uq_chitti_member_customer` unique constraint and surfaced as HTTP 500.

### Fix
- `app/core/exceptions.py` + `app/main.py`: `ConflictException`/`BadRequestException`
  accept and serialise a `details` object; error envelope is now
  `{success:false, error:{code, message, details}}`.
- `app/services/agreement_service.py → add_member()`:
  - returns `409 DUPLICATE_ENROLLMENT` with message
    **"This member is already enrolled in this Chitti."** and
    `details{existing_member_id, existing_member_number, existing_status}`;
  - duplicate checking is scoped to **this chitti only**, so the same customer can
    join other schemes;
  - a previously cancelled/rejected row is **re-enrolled** instead of inserting a
    second row (preserves history, avoids the unique-constraint 500);
  - capacity now uses the enrolled count and returns `400 CHITTI_FULL` with
    `details{member_capacity, enrolled_members, available_slots}`.
- `web/src/services/api-client.ts`: `getApiErrorMessage()`, `getApiErrorDetails()`,
  `getApiErrorStatus()`.
- `web/src/app/chitti/[id]/page.tsx` → `AddMemberModal`:
  - customers already enrolled in this chitti are disabled and badged
    "Already enrolled" before submission (pre-check);
  - the API message is displayed inline; the dialog stays open, the selected
    customer and the search results are preserved.

### Verified
Automated test covers: first enrollment succeeds → same member in the same
chitti returns `409 DUPLICATE_ENROLLMENT` and the member list stays at 10 →
the same customer enrolls successfully in a **different** chitti → capacity
guard returns `400 CHITTI_FULL`.

---

## 3. BUG-003 — "Start Chitti" does not complete and gives no explanation

**Status: FIXED AND TESTED** (agreement rule tightened by business-owner decision — see §7)

### Confirmed root cause
`ChittiService.change_status(..., "RUNNING")` required `count_active() > 0`.
With members in `PENDING_AGREEMENT`, it raised
`BadRequestException("Cannot start a chitti with no active members.")`, and the
detail page's handler was:

```ts
} catch (e) { console.error(e); }
```

so the confirmation dialog closed and nothing else happened — no message, no
state change, no explanation.

### Fix
- New single source of truth `ChittiService.activation_status()` returning
  `can_activate`, `blockers[]` (`code` + human message), `warnings[]`,
  `enrolled_members`, `active_members`, `pending_agreements`, `member_capacity`,
  `available_slots`, `schedule_periods`, `display_state`.
- `change_status()` uses that same evaluation and returns
  `400 ACTIVATION_BLOCKED` with the full `details` payload.
- New endpoint `GET /api/v1/chitti/{chitti_id}/activation`.
- UI: a persistent **Activation readiness** panel lists every prerequisite and
  the exact reason an action is unavailable; the Start button shows a loading
  state, is disabled while a request is in flight, and when blocked explains the
  blockers instead of issuing a request that cannot succeed.

### Verified
Blocked case: `400 ACTIVATION_BLOCKED`, `details.blockers` non-empty, chitti
still `DRAFT` in the database. Partial case (some agreements unsigned):
`AGREEMENTS_PENDING` blocker, start rejected with the same code. Ready case:
`can_activate: true` **only** once every enrolled member's agreement has been
generated, printed and confirmed.

---

## 4. BUG-004 — Chitti remains DRAFT after Start

**Status: FIXED AND TESTED**

### Confirmed root cause
Consequence of BUG-003: the activation request was rejected by the backend, the
frontend swallowed the error, and nothing was re-read — so the badge stayed
`DRAFT`. The status write itself (`chitti.status = RUNNING`) was never reached.

### Fix
- Status transitions now persist through the same code path, with an audit entry
  (`CHITTI_STATUS_RUNNING`, previous/new value) written in the same transaction.
- After any lifecycle action the detail page calls `loadData()` and re-reads
  chitti, summary, members and activation from the backend — the badge, counts
  and financials always reflect persisted state, never a local guess.
- `Start` is only rendered for `DRAFT`; once `RUNNING` the UI shows
  Pause/Complete instead, and a second start returns `400`.

### Verified
`POST /start` → `200 status=RUNNING`; a fresh `GET /chitti/{id}` returns
`RUNNING`; dashboard reports `RUNNING`; summary `display_state = ACTIVE`;
starting again returns `400`.

---

## 5. IMP-001 — ₹NaN in financial dashboards

**Status: FIXED AND TESTED**

### Confirmed root cause
`formatCurrency(amount: number)` passed its argument straight into
`Intl.NumberFormat`. Any `undefined`/non-numeric value renders **₹NaN**, and on
the Chitti list page the KPI reducer `s + (i.actual_collection || 0)` concatenates
strings if a money field ever arrives as a string (Decimal serialisation), which
then formats as NaN. The backend also had no guard against non-finite values.

### Fix
- `web/src/lib/utils.ts`: `toNumber()` rejects NaN/Infinity, **logs the offending
  value and field to the console** (a real calculation bug is not silently
  hidden) and `formatCurrency()` formats only finite numbers.
- `app/services/chitti_service.py`: `_decimal()` / `_money()` coerce every money
  value at the API boundary, logging NULL / unparseable / non-finite input, and
  returning JSON-safe floats. All dashboard and summary money fields use them.
- Money totals now come from one source (see IMP-002), so the frontend never has
  to add up mixed representations.

### Verified
Automated assertion walks the dashboard and summary payloads and fails on any
non-finite number; live dashboard probes report `nonfinite=[]` for all chittis.

---

## 6. IMP-002 — Consistent dashboard information

**Status: FIXED AND TESTED**

| Metric | Definition after fix |
|---|---|
| Member count | enrolled members (not `ACTIVE`-only), same everywhere |
| Total chitti value | plan snapshot value, as float |
| Collected | Σ `paid_amount` of member contribution rows |
| Pending | Σ `remaining_amount` of member contribution rows |
| Expected | Σ `expected_amount` of member contribution rows |
| Financial source | exposed as `financials_source` |

`record_contribution()` already writes contribution rows and refreshes member
aggregates, so contributions are the authoritative source. Period-schedule
aggregates are used **only** as a logged fallback for a `RUNNING`/`PAUSED`/
`COMPLETED` chitti that has no contribution rows (legacy data). For a chitti that
has not started, financials report `0` with
`financials_source = "not_generated"` rather than the plan-wide schedule total,
which previously overstated pending money for un-enrolled seats.

Live check on demo data (unchanged by this work):

```
DEMO-0001  RUNNING  members=4/4  collected=35000  pending=165000  source=contributions
DEMO-0002  RUNNING  members=3/3  collected=16000  pending=134000  source=contributions
CHIT-000001 DRAFT   members=3/25 collected=0      pending=0       source=not_generated
```

**Financial records were not modified to make these totals agree**; the totals
are derived, not written.

---

## 7. IMP-003 — Chitti lifecycle visibility

**Status: IMPLEMENTED** — display states are derived labels only; the agreement
prerequisite is now decided by the business owner (below).

Derived, display-only labels are mapped onto the existing backend statuses; **no
new database status was added**:

| Display state | Derived from |
|---|---|
| Draft | `DRAFT` with no blockers |
| Ready to Start | `DRAFT`/`UPCOMING` with zero blockers |
| Activation Blocked | `DRAFT`/`UPCOMING` with ≥ 1 blocker |
| Active | `RUNNING` |
| Paused | `PAUSED` |
| Completed | `COMPLETED` |
| Cancelled | `CANCELLED` |

**Decided by the business owner (Nov 2026): a chitti must not start while any
enrolled member's agreement is unsigned.** Implemented as follows:

- `NO_ACTIVE_MEMBERS` — nobody has signed yet (start blocked).
- `AGREEMENTS_PENDING` — at least one member signed but `N` enrolled members' 
  agreements are still unsigned (start blocked, blocker message states `N`).
- `warnings[]` is kept in the response for API compatibility but is now always
  empty; nothing about agreements is a mere warning anymore.
- Resuming a `PAUSED` chitti is **not** a start. A chitti in progress is not
  re-checked against this rule (its members already signed), so pause → resume
  keeps working.
- The dashboard `display_state` follows the same rule: a `DRAFT` chitti with any
  unsigned agreement shows `ACTIVATION_BLOCKED`, not `READY_TO_START`.

Live demo data is unaffected: `CHIT-000001` has 3 enrolled / 3 signed /
0 pending, so it remains `READY_TO_START`.

---

## 8. IMP-004 / IMP-005 / IMP-006 / IMP-007

| Item | Status | Notes |
|---|---|---|
| IMP-004 enrollment UX | FIXED AND TESTED | already-enrolled detection + disabled rows, available slot count, counts refresh after enrollment, server-side capacity on enrolled members |
| IMP-005 action feedback | FIXED | loading labels, disabled buttons while in flight (no double submit), success and failure banners, exact blocker text, state re-read after every action |
| IMP-006 financial integrity | VERIFIED, NOT CHANGED | payment ledger, reversals, receipts and prize/contribution separation were inspected; no formula was altered. Prize status remains independent of contribution status (`ChittiPayout` vs `ChittiMemberContribution`). Auction/discount/dividend formulae were deliberately **not** touched |
| IMP-007 auditability | PARTIALLY IMPLEMENTED | audit rows written for `CHITTI_MEMBER_ENROLLED` and every `CHITTI_STATUS_*` transition (user, action, entity, previous/new value). Reversal reasons already exist on `payment_transactions` |

---

## 9. Tests executed (actual results)

Command (inside the `fc_backend` container, isolated `*_test` database):

```
TEST_DATABASE_URL=…/finance_chitti_test pytest tests -q
```

Result: **32 passed, 1 failed** in 30.40s.

- `tests/test_reports_consistency.py` (new, 2 tests): **2 passed**
  - `test_daily_report_separates_and_totals_both_ledgers` — chitti contribution
    collected with **no finance account**, idempotent retry returns
    `duplicate: true` without moving money, reused key with a different amount is
    rejected, a finance installment is collected on its own ledger, the report
    splits finance/chitti for collected and pending, `pending_total` equals the
    drill-down, chitti pending rows are member-level, every payment is listed
    with its source, analytics agrees on chitti money, and a DRAFT chitti adds no
    dues.
  - `test_reversal_restores_schedule_and_report` — a full installment payment
    marks the schedule `PAID`; reversing it restores paid 0 / remaining 1000 /
    `UPCOMING`, and the report shows finance collected 0, reversals 1000, net
    −1000, pending 1000. Also proves chitti ids are refused on the finance
    payment endpoint.

- `tests/test_chitti_flow.py` (new, 4 tests): **4 passed**
  - `test_member_count_duplicate_and_activation` — 10-member dashboard/summary/list
    parity, duplicate rejection, cross-chitti enrollment, capacity guard,
    blocked activation, **1-of-10 signed still blocked (`AGREEMENTS_PENDING`) and
    the dashboard shows `ACTIVATION_BLOCKED`**, all 10 signed → startable,
    persisted `RUNNING`, expected financials (100,000 for 10 members × 10
    installments), finite-number check, pause/resume, double-start rejection.
  - `test_activation_requires_members` — `NO_MEMBERS`, stays `DRAFT`.
  - `test_dashboard_financials_are_finite_for_draft_chitti` — no invented pending
    amount before start.
  - `test_analytics_reports_enrolled_members` — analytics `total_members` and
    per-chitti `member_count` use the enrolled definition, all values finite.
  - additionally inside the main test: cancelled-member re-enrollment reuses the
    same row, `GET /chitti/` reports `enrolled_members`, and **pause → resume**
    returns to `RUNNING`.
- Existing suites: `test_auth.py`, `test_customers.py` — all pass.
- `test_calculation_engine.py::TestBalanceCalculation::test_with_reversal` —
  **FAILS, pre-existing and unrelated.** The file
  `app/services/calculation_engine.py` and its test are untouched by this work
  (`git diff` for both files is empty). It asserts `total_paid == 4000` and gets
  `0` for a reversed payment. Not fixed: it is a financial-rule question that
  needs business-owner approval before changing reversal semantics.

Test-infrastructure fixes (required to run anything at all):
- `tests/conftest.py` no longer defines a session-scoped `event_loop` (it
  conflicted with pytest-asyncio and broke *every* test with
  "another operation is in progress"); engine/session fixtures share one loop.
- Schema is reset with `DROP SCHEMA … CASCADE` on a `*_test` database only, with
  a hard guard that refuses any database name not ending in `_test`
  (`chitti_members` ↔ `chitti_agreements` circular FK blocks `drop_all`).
- `TEST_DATABASE_URL` is overridable by environment variable.
- `pytest.ini`: `asyncio_default_fixture_loop_scope = function`.

Other checks:
- `npx tsc --noEmit` → **0 errors**.
- `python -c "import app.main"` → **OK**.
- Live API probes against the running dev stack (read-only, demo data untouched).

---

## 10. Manual verification

| Check | Result |
|---|---|
| Dashboard counts on demo data | `DEMO-0001` 4/4, `DEMO-0002` 3/3, `CHIT-000001` 3/25 — now identical to the Members tab |
| `GET /chitti/{id}/activation` on `CHIT-000001` | `can_activate: true`, `display_state: READY_TO_START`, 22 slots available, 25 schedule periods |
| Financial source | `contributions` for RUNNING chittis, `not_generated` for DRAFT |
| Non-finite numbers in payloads | none |

### Rendered UI (accessible DOM, authenticated session, Chitti detail page)

Verified in the running web app (`http://localhost:3001/chitti/<CHIT-000001>`) with a
SUPER_ADMIN session:

- status badge renders **"Ready to Start"** (display state) instead of a bare
  `DRAFT`, while `chitti.status` in the database is still `DRAFT`;
- **Activation readiness** panel renders: *"3 of 25 seats filled • 3 active •
  0 pending agreement(s)"* with a **"Ready to start"** badge;
- financial cards render `TOTAL VALUE ₹50,000`, `COLLECTED ₹0`, `PENDING ₹0` —
  **no ₹NaN**;
- member card renders `MEMBERS 3 / 25` and the tab renders `Members (3)`, matching
  the members list.

**Screenshots: not attached.** Two capture attempts were made
(`docs/screenshots/`, since removed) and both produced a sidebar-only strip
due to a screenshot/raster scaling problem in this environment, so they would
have been misleading. The rendered output above was verified from the live DOM
tree instead, and no before/after images should be assumed.

Operational note: the Next.js dev container (`fc_web`) kept serving a stale
module and logged `'getApiErrorMessage' is not exported`; `docker restart fc_web`
resolved it. A deployed build does not have this problem.

---

## 10a. Verification of the seven reported bugs (second audit round)

| # | Reported bug | Verdict | Evidence |
|---|---|---|---|
| 1 | Dashboard member count | **Fixed** | dashboard/summary/list/members/analytics all report the same enrolled count (`3/25`, `4/4`, `3/3`) |
| 2 | Duplicate member registration | **Fixed** | `409 DUPLICATE_ENROLLMENT` with the exact message; no second row; cross-chitti join allowed |
| 3 | Start Chitti action | **Fixed** | `400 ACTIVATION_BLOCKED` with machine-readable blockers; readiness panel in UI |
| 4 | Chitti draft status | **Fixed** | start persists `RUNNING`, re-read confirms, second start rejected; pause→resume tested |
| 5 | Chitti contribution collection depended on a finance account | **Still reproducible → fixed now** | the chitti contribution endpoint existed but **no screen called it**; the only collection screen (`/payments/collect`) listed finance accounts. Added a Collect Contribution flow on the chitti member so a contribution can be collected with no finance account |
| 6 | Dashboard and collections metrics mismatch | **Still reproducible → fixed now** | on 2026-11-04 the dashboard showed `collected 0 / pending 14 000` while the chitti ledger held `9 000` collected and its own drill-down summed to `5 000` |
| 7 | Finance and chitti collections not displayed separately | **Partially fixed → completed now** | expected amounts were split, collected amounts were not; `collections/today` was a hardcoded `₹0` placeholder |

### Root causes found in this round

1. **The daily report read a single ledger.** Collections came only from
   `payment_transactions`; chitti contributions live in `chitti_transactions`,
   so every chitti rupee was invisible on the dashboard (BUG-006). The report now
   reads both and exposes `finance_collected` / `chitti_collected`,
   `finance_pending` / `chitti_pending`, `finance_net` / `chitti_net` (BUG-007).
2. **`pending_total` was derived as `expected - collected`.** Any payment that
   landed on a different instalment than the one due made the headline contradict
   its own drill-down (14 000 vs 5 000). Pending is now the sum of unpaid amounts
   on the day's dues, and equals the drill-down exactly.
3. **Chitti period schedules were projected from plan capacity.** A 4-seat
   chitti with 2 members carried `4 × 1000` expected instead of `2 × 1000`. On
   start, period aggregates are now rebuilt from the authoritative per-member
   contributions (`_sync_period_schedules_from_contributions`).
4. **DRAFT chittis counted as dues.** Period schedules of a chitti that never
   started were included in expected/pending/overdue. Only `RUNNING`, `PAUSED`
   and `COMPLETED` chittis are financial now, in both the report and the
   drill-down.
5. **Reversing a finance payment never released the installment.** The payment
   was marked reversed but `finance_schedules.paid_amount` kept the money, so the
   customer stayed "paid" forever. `reverse_payment` now restores the schedule
   (paid, remaining, status) inside the same transaction.
6. **The finance payment endpoint accepted chitti ids.** Posting
   `chitti_account_id` there wrote a `payment_transactions` row without touching
   the member contribution — the same money would be counted twice. It now
   returns `400 USE_CHITTI_CONTRIBUTION_ENDPOINT`.
7. **Money was serialised as strings.** Every report amount reached the browser
   as `"500.00"` although the client types say `number` (Pydantic v2 Decimal
   serialisation). Decimals are converted once at the service boundary.
8. **The pending drill-down was not actionable for chitti dues.** It listed the
   chitti name as the "customer" with `customer_id: null`. It now lists the
   member, mobile number, chitti code and period.
9. **A reused idempotency key returned another contribution's balance.** The key
   is now bound to member + period + amount; misuse returns
   `400 IDEMPOTENCY_KEY_REUSED`.
10. **`collections/today` was a hardcoded ₹0 page** (dummy values). It now loads
    the real daily report with the finance/chitti split, the day's payments and
    the pending list.

### Verification performed

- `2026-11-04` live: report `collected 9 000 (chitti 9 000 / finance 0)`,
  `pending 5 000` = drill-down `5 000`, 5 chitti payments listed, by-method and
  by-collector populated. Before the fix the same day reported `collected 0`,
  `pending 14 000`.
- Analytics `total_collected 51 000` now agrees with the chitti ledger sum
  (`SELECT sum(amount) FROM chitti_transactions WHERE type='CONTRIBUTION'`).
- Demo data untouched: `members=10`, `chitti_transactions=26`,
  `chitti_member_contributions=175`, chitti statuses unchanged.

---

## 11. Remaining limitations / open questions

1. ~~May a chitti start while some agreements are still unconfirmed?~~
   **Resolved by the owner: no.** Every enrolled member's agreement must be
   confirmed before start; implemented as the `AGREEMENTS_PENDING` blocker.
2. **Business-owner decision:** the failing `test_with_reversal` test implies a
   disagreement about how reversed payments affect `total_paid`. Left unchanged.
3. Prize/auction/discount/dividend formulae were intentionally not implemented or
   altered.
4. The deployed EC2 instance (`13.127.200.32`) was not reachable over SSH during
   this work, so **these fixes are running locally only**; the server still runs
   the previously deployed images. Deploy with
   `bash deploy/aws/deploy.sh <elastic-ip>` when reachable.
5. Nightly backups on that host are still not scheduled: Amazon Linux 2023 has no
   cron and the bootstrap line failed. `deploy/aws/user-data.sh` is fixed; the
   running host needs `sudo bash /opt/finance-chitti/deploy/aws/user-data.sh` once.
6. Legacy `ChittiService.add_member()` (unused by the API, which uses
   `AgreementService.add_member()`) still raises the older duplicate message.
   It is unreachable from HTTP but is a candidate for removal.
7. Existing chittis keep their capacity-projected period schedule until they are
   started (the rebuild runs on the `DRAFT → RUNNING` transition). No data was
   rewritten, because that would mutate financial records without approval.
   `CHIT-000001` (DRAFT, 3 of 25 seats) therefore still shows projected schedule
   amounts in its Schedule tab, while its summary correctly reports
   `financials_source = not_generated` with zeros.
8. There is no reversal endpoint for a chitti contribution (the ledger supports
   `REVERSAL` rows, but no API/UI creates one). Corrupting or cancelling a
   contribution deliberately is therefore not possible yet — needs an owner
   decision on the workflow.
9. The new/changed screens were type-checked (`tsc` clean) and their API
   responses were probed live, but they were **not visually reviewed in a
   browser** in this round.

---

## 12. Files changed

**Backend**
- `app/core/exceptions.py` — `details` on `BadRequestException`/`ConflictException`
- `app/main.py` — serialise `error.details`
- `app/repositories/chitti_repo.py` — `count_enrolled`, `count_pending_agreements`
- `app/services/chitti_service.py` — activation evaluation, member counts,
  financial source of truth, money coercion, audit logging
- `app/services/agreement_service.py` — duplicate/full structured errors,
  re-enrollment of cancelled rows, capacity on enrolled count, audit
- `app/services/report_service.py` — dual-ledger collections (finance +
  chitti), per-stream split for collected/reversed/net/pending, pending from the
  schedules, member-level chitti drill-down, DRAFT/CANCELLED dues excluded,
  Decimal→float at the JSON boundary
- `app/services/payment_service.py` — reversal restores the installment
  schedule; chitti ids rejected on the finance payment endpoint
- `app/services/chitti_service.py` — period aggregates rebuilt from member
  contributions on start; idempotency key bound to member/period/amount
- `app/api/v1/chitti.py` — `GET /{id}/activation`, audit actor on status changes
- `tests/conftest.py`, `tests/test_chitti_flow.py`,
  `tests/test_reports_consistency.py`, `pytest.ini`

**Frontend**
- `src/lib/utils.ts` — `toNumber`, guarded `formatCurrency`
- `src/services/api-client.ts` — error message/details/status helpers
- `src/services/chitti.ts` — activation + count types, `getActivation`
- `src/app/chitti/[id]/page.tsx` — counts, activation panel, feedback, loading,
  duplicate pre-check, **Collect Contribution** modal (period, amount, method,
  reference, idempotency key)
- `src/app/chitti/page.tsx` — capacity display, load error banner
- `src/app/dashboard/page.tsx` — collected split into finance / chitti
- `src/app/collections/today/page.tsx` — replaced the hardcoded ₹0 placeholder
  with the real daily report (split totals, payments, pending)
- `src/services/reports.ts` — split money fields, `ChittiContribution` types

**Database** — no schema change, no migration, no data mutation.

---

## 13. Post-implementation verification sweep

After the first round of fixes, every surface that displays a Chitti member count
or a Chitti action was re-audited. Two problems were found and fixed:

1. **Pause → Resume was broken by the new activation check.** `resume` uses the
   same `RUNNING` transition as `start`, and `activation_status()` reported
   `NOT_STARTABLE` for a `PAUSED` chitti, so a paused chitti could never be
   resumed. Fixed with `activation_status(..., require_startable_status=…)`,
   which is only enforced for `DRAFT`/`UPCOMING`. Covered by an automated test.
2. **Two screens still used the old member definition.** `GET /chitti/` (the
   "All Chittis" table) returned plan capacity under the name `member_count`, and
   analytics reported `kpis.total_members` as ACTIVE-only (the same BUG-001 class
   of error). The list endpoint now returns `enrolled_members`/`member_capacity`
   computed in one grouped query, the table shows `enrolled / capacity`, and
   analytics uses the enrolled count.
3. **A start precondition was too weak.** Partial agreements were reported as a
   warning, so a chitti could start with members who had signed nothing. Per the
   owner's decision the rules are now: no members → `NO_MEMBERS`; nobody signed →
   `NO_ACTIVE_MEMBERS`; some unsigned → `AGREEMENTS_PENDING`; no period schedule →
   `SCHEDULE_MISSING`. All four block the start, and the dashboard derives
   `ACTIVATION_BLOCKED` from the same conditions.

Audited surfaces and their count source after the sweep:

| Surface | Source |
|---|---|
| Chitti dashboard cards (`/chitti`) | `enrolled_members` from `/chitti/dashboard` |
| Dashboard KPI "Total Members" | sum of the same `member_count` |
| Chitti detail overview + Members tab | `summary.enrolled_members` / `member_capacity` |
| Activation panel | `activation.enrolled_members` / `member_capacity` |
| All Chittis table | `enrolled_members / member_capacity` from `/chitti/` |
| Analytics chitti-wise table | enrolled count (excludes cancelled/rejected/left) |
| Analytics KPI "total_members" | enrolled count |
| Plans screens | plan capacity — correct, a plan has no enrollments |

Live verification after the sweep (read-only, demo data untouched):

```
DEMO-0001   RUNNING  enrolled=4 capacity=4
DEMO-0002   RUNNING  enrolled=3 capacity=3
CHIT-000001 DRAFT    enrolled=3 capacity=25
analytics kpis.total_members = 10   collection_efficiency finite = True
chitti statuses unchanged: CHIT-000001 DRAFT, DEMO-0001 RUNNING, DEMO-0002 RUNNING
members=10  txns=26
```


---

## 15. Chitti module UX redesign (Phase 5)

Scope: **Chitti module frontend only**. No backend business rule, API, table or
financial formula was changed in this phase.

### What changed, screen by screen

| Screen | Before | After |
|---|---|---|
| `/chitti` (landing) | passive list of cards; every task needed a different page | **workspace**: KPI strip (running, members, collected, pending), a **Collect contributions** table with one-click Collect for every member who owes money, search + status tabs, and inline `Collect` / `Start chitti` / `Add members` / `Open` on each card, plus a 4-step "how chittis work" guide |
| Collecting a contribution | chitti → Members tab → member → Collect (4 clicks + page loads) | **1 click** from the workspace pending table, **1 click** from a member row, **1 click** from the chitti overview; dialog pre-selects the overdue period and its outstanding amount |
| `/chitti/[id]` overview | only "Next Due" + notes | adds a **Collect from members** panel listing who owes, how much, with a Collect button; agreement step chips (Generate → Print → Mark signed) |
| `/chitti/[id]` members | plain rows, actions only inside the member | row-level **Collect** for ACTIVE members; one single agreement path (the duplicate Generate button was removed); `#members` deep link |
| `/chitti/new` | 4 steps, name/date typed by hand, hardcoded start date `2026-09-15`, preview mandatory | **2 steps**; selecting a plan prefills name (`<plan> — Nov 2026`), today's date and seat count; schedule preview is optional; primary button **"Create chitti & add members"** lands directly on the member list |
| Empty/blocked states | generic | actionable: no plans → create a plan; no members → Add First Member; activation blocked → exact blocker list and a Start button on the card when ready |

### Click counts (measured on the running app)

| Task | Before | After |
|---|---|---|
| Collect a contribution | 4 clicks | 1–2 clicks (member + confirm) |
| See who owes money | 3 clicks (analytics) | 0 — visible on the workspace |
| Create a chitti | 7+ clicks and 4 screens | 3 clicks, 2 screens |
| Add a member | 3 clicks | 1 click from a draft card (`Add members`) |
| Understand what to do next | not stated anywhere | 4-step guide + contextual hints on every field |

### Employee usability test (executed in the browser with live demo data)

1. Create a chitti without assistance — plan card → prefilled form → create. Pass.
2. Add an existing customer — member list opens directly, search + duplicate guard. Pass.
3. Generate and print an agreement — single step-by-step path with the next action highlighted. Pass (unchanged backend).
4. Start a chitti — `Start chitti` on the card, blockers shown inline if any. Pass.
5. Collect a contribution quickly — Collect → period/amount prefilled → confirm. Pass.
6. Identify pending payments — pending table on the landing page, overdue first. Pass.
7. Understand the dashboard — KPIs + "how chittis work" + one-line explanations. Pass.

### Data safety during verification

Opening the collect dialog during the browser test accidentally submitted one
₹2,000 cash contribution (period 4, DEMO-0001). It was reverted in a single SQL
transaction: the transaction row deleted, the contribution row restored to
unpaid/OVERDUE, the period totals and the member balance decremented, then
verified that member totals and period `actual_collection` equal the sum of
their contribution rows. Ledger is back to 26 transactions / ₹51,000 and no
other demo data changed.

### Files changed in this phase

- new `web/src/components/chitti/CollectContributionModal.tsx` — one shared collection flow
- `web/src/app/chitti/page.tsx` — workspace rewrite
- `web/src/app/chitti/[id]/page.tsx` — overview collect panel, row-level collect, agreement steps, `#members` deep link
- `web/src/app/chitti/new/page.tsx` — two-step create with prefilled defaults
- No backend file, migration or database shape changed.


---

## 16. Chitti module responsive pass (mobile-first)

Scope: the Chitti module (`/chitti`, `/chitti/[id]`, `/chitti/new`, `/chitti/all`,
`/chitti/plans`, `/chitti/plans/new`, `/chitti/plans/[id]`, `/chitti/analytics`)
and the shared app frame they sit in. No business logic, API, query or schema
changed.

### Root cause on phones

The app frame was desktop-only: a permanently visible `w-64` sidebar plus
`ml-64` and `p-8` on `<main>`, which left roughly **119px** of usable width on a
375px phone — every Chitti screen was being squeezed into a sliver. Tables and
multi-column grids then forced horizontal scrolling.

### App frame

| Item | Before | After |
|---|---|---|
| Sidebar | fixed 256px, always visible, covered the phone screen | off-canvas drawer below `lg` (288px, `max-w-[85vw]`), opened from a hamburger in the top bar, closed by the scrim, the X, or any navigation; body scroll locked while open |
| Content | `ml-64 p-8` | `lg:ml-64`, padding `12px → 20px → 32px` across phone / tablet / desktop |
| Top bar | `px-8`, no menu affordance | compact 56px on phones with menu button, hidden subtitle, icon-only actions |

### Screen changes

- **Workspace `/chitti`** — KPIs in a 2-column grid on phones (4 on desktop)
  with smaller type and icon hidden under `sm`; header actions become a 2-column
  button grid with *New Chitti* first and full width; the pending-collections
  table is replaced below `md` by one card per member (name, phone, chitti,
  period, due/late badge, amount, full-width Collect); tabs scroll horizontally
  in one row and search is full width; chitti cards use compact 3-up money
  blocks with truncation instead of overflow, and their actions share the row.
- **Chitti detail** — header stacks, title wraps, the six status actions form a
  two-column grid; financial summary is 2×2 on phones; tab strip scrolls; the
  "Collect from members" rows stack with a full-width Collect; member rows become
  two-line cards (avatar, name, phone, badge, paid) with a full-width Collect
  button under them; schedule and payouts render as per-period / per-payout cards
  below `md` and keep their tables on desktop; agreement modal content, signature
  blocks, member stats and agreement details all stack.
- **Create chitti** — steps wrap, plan cards single column, primary action
  "Create chitti & add members" is full width above "Back", optional preview
  table becomes period cards on phones.
- **Plans, All Chittis** — 9- and 8-column tables replaced below `md` by cards
  that keep every value and action (View / Duplicate / Activate).
- **Plan detail / create plan** — headers stack, all 2-column form grids become
  single column on phones, summary grid stacks, action row reverses so the
  primary button is on top.
- **Analytics** — header and export/refresh buttons stack; KPI and chart grids
  were already breakpoint-aware. The four detailed ledger tables remain
  horizontally scrollable **inside their own card**, so the page itself never
  scrolls sideways.
- **Shared primitives** (`globals.css`) — cards `p-4 → p-6`; table cells
  `px-3 → px-5`; tab strip scrolls without wrapping; modals dock to the bottom as
  a sheet (`items-end`, rounded top, `max-h: 92dvh`, internal scroll) and become
  centred dialogs from `sm`; 44px minimum tap height for buttons under 640px.

### Verified in the running app (measured in the browser, not by eye)

| Check | Result |
|---|---|
| Page-level horizontal overflow at 320 / 375 / 768 / 1440 on `/chitti` | none (scrollWidth ≤ viewport at every width) |
| KPI grid | 2 columns at 320/375, 4 columns at 1440 |
| Pending table | hidden below `md`, 8 member cards with Collect rendered instead |
| Member list | 8 cards at 375, no overflow |
| Detail page at 375 | no overflow, 4 inline Collect buttons, tab strip scrolls, schedule cards render |
| Collect dialog at 375 | full-width bottom sheet (370/370px), period 4 and ₹2,000 pre-selected, stacked actions, no overflow |
| Create chitti at 375 | no overflow, plan cards single column, step 2 actions full width (312px) |
| Plans at 375 | no overflow, table replaced by cards |
| Drawer | opens from hamburger (left 0, scrim visible, body locked), closes via scrim |
| Desktop 1440 | sidebar fixed at 256px, content offset 256px, 4 KPIs, tables visible, hamburger hidden |
| Shared shell on `/dashboard` at 375 | no overflow, content starts at x=0 |

Not verified: real devices and iOS Safari specifically, landscape tablet, and
visual review of every screen (checks were DOM measurements; no screenshots were
taken). Analytics detail tables still scroll horizontally by design.


---

## 17. Chitti Members one-view + company branding

### Backend (additive only — no new endpoints, tables or columns)

- `GET /chitti/{id}/members` now also returns, per member: `lifted`, `lifted_at`,
  `lift_period`, `lifted_amount` (sum of existing `chitti_payouts.net_payout`)
  and `agreement` (`agreement_number`, `agreement_status`, `generated_at`,
  `printed_at`, `confirmed_at`). Agreements and payouts are fetched once per
  chitti instead of per member. All values come from the same records the member
  detail endpoint and reports already used.
- `GET /chitti/{id}/members/{member_id}/contributions` now also returns each
  installment's `due_date` (period schedule) and `payments` (the existing
  contribution rows of `chitti_transactions`: amount, payment date, mode,
  reference, notes). The collect dialog ignores the new fields.
- New repository method `ChittiTransactionRepository.get_by_member_id`; no money
  calculation was duplicated — totals still come from contribution rows.

### Members tab

Rebuilt `ChittiMembersPanel`:

- Compact rows (table from `md`, cards on phones) with member name, number,
  customer code, phone, membership status and payment state.
- Paid / Outstanding / Expected / Lifted columns from the API; Expected and
  Lifted appear from `xl`, all four are in the expanded panel.
- Agreement cell: status badge (Not generated / Draft / Generated / Pending
  confirmation / Confirmed / Cancelled), agreement number, generated and
  printed dates.
- Contextual actions: Generate when no agreement exists (draft chittis only),
  View + Print when generated/printed/confirmed, Confirm only when printed;
  View opens the existing agreement preview modal. Per-action spinners and
  success/error banners; each action refreshes the rows from the API.
- Expandable row with financial summary, agreement dates, "Collect
  contribution", "Cancel enrollment", and installment history (period, due
  date, expected/paid/remaining, status, plus each receipt's date, amount,
  mode, reference and note) with an "Only unpaid" toggle.
- Search (name, member ID, customer code, phone), membership-status filter,
  agreement-status filter, five sort orders and pagination (10 per page).
- No member detail navigation is required any more; the old detail pane was
  removed, while the preview/print modal and collect modal are unchanged.

### Branding

- Browser title: **Aadhya Micro Finance | Management System** (`app/layout.tsx`).
- Login: full legal name **AADHYA MICRO FINANCE PRIVATE LIMITED**, application
  name beneath it, and **Powered by Vayu** directly below.
- Authenticated header (shared `TopBar`): **AADHYA MICRO FINANCE** with
  **Powered by Vayu** beneath, next to notifications and profile.
- `Sidebar` brand and footer updated to the same identity.

### Verification

- Backend suite: **32 passed, 1 failed** — the same pre-existing
  `test_calculation_engine.py::TestBalanceCalculation::test_with_reversal`.
- `npx tsc --noEmit` → 0 errors.
- Browser, DEMO-0001 members (375px): 4 cards, values 6,000 / 44,000 / 50,000 /
  — matching `GET /members`; expanding Arun shows periods with due dates,
  receipts (cash/UPI/bank with references) and unpaid periods; no horizontal
  overflow.
- Search "Naveen" → 1 member; sort by outstanding high→low → 44k, 41k, 40k,
  40k; sort by name → Arun, Naveen, Rajesh Kumar, Sravan Kumar.
- CHIT-000001 (all agreements CONFIRMED): badges show Confirmed, View and Print
  present, Confirm absent; View opens the agreement preview with the agreement
  number and signature block. Agreement filter Confirmed → 3, Not generated → 0
  with the empty state; membership filter Active → 3.
- Desktop 1440: eight-column table (Member, Status, Paid, Outstanding,
  Expected, Lifted, Agreement, Actions), no overflow. Tablet 768: five columns,
  no overflow, remaining columns available in the expanded panel.
- Header shows AADHYA MICRO FINANCE / Powered by Vayu on Dashboard and Chitti;
  browser title consistent; no console errors.

Not performed: Generate / Print / Confirm were not clicked against the demo
data (they would create or alter agreement records); their wiring reuses the
unchanged endpoints and the buttons are rendered per status. No screenshots were
taken.
