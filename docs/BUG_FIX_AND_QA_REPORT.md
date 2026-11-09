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

Result: **30 passed, 1 failed** in 27.62s.

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
- `app/api/v1/chitti.py` — `GET /{id}/activation`, audit actor on status changes
- `tests/conftest.py`, `tests/test_chitti_flow.py`, `pytest.ini`

**Frontend**
- `src/lib/utils.ts` — `toNumber`, guarded `formatCurrency`
- `src/services/api-client.ts` — error message/details/status helpers
- `src/services/chitti.ts` — activation + count types, `getActivation`
- `src/app/chitti/[id]/page.tsx` — counts, activation panel, feedback, loading,
  duplicate pre-check
- `src/app/chitti/page.tsx` — capacity display, load error banner

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
