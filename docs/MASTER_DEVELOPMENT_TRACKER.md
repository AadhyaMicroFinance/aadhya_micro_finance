# Aadhya Micro Finance â€” Project Knowledge and Verification Tracker

Updated: 2026-11-14
Repository: `D:\Naveen\aadhya_micro_finance`
Branch/base commit: `main` / `df20963`
Delivery state: local working changes only; no push or deployment.

## A. Project history and timeline

The application is the Aadhya Micro Finance Pvt Ltd web system for customer/member administration, Finance accounts, Chitti (rotating savings) operations, collections, payments, agreements and reports. The source currently present is a FastAPI backend, PostgreSQL/SQLAlchemy database layer and Next.js 14/React/TypeScript web client. README describes mobile, Redis/Celery and a broader roadmap; corresponding mobile/background worker modules are not present in this checkout and that README architecture/phase list is stale relative to source.

Relevant history reviewed:

| Commit | Recorded subject | Change evidenced by commit contents |
|---|---|---|
| `1b40cca` | Naveen Bugs Fixed | Introduced the BUG-001â€“004 history/report, enrolled-member count/readiness/status work, agreement service and Chitti regression suite. |
| `b3d4095` | Agreement bug fixed | Follow-up changes to Chitti activation behavior and its regression expectations. |
| `90260c7` | Naveen bugs fixed | Expanded Finance/Chitti report and ledger reconciliation, payment reversal handling, collection UI and related regression tests. |
| `df20963` | Naveen bugs fixed 1 | Added the dedicated inline Members panel, related member data/API support, login/layout branding and Chitti detail changes. |

Those fixes were present in the baseline and were not reapplied as new work. `docs/BUG_FIX_AND_QA_REPORT.md` contains earlier root-cause history. Its historical claim of testing against `finance_chitti_test` is not the database used in this verification run.

## B. Business requirements recovered

- Manage customers/members and distinguish membership from Finance borrowing.
- Support daily, weekly and monthly Chittis, contributions, period schedules, payout/winner administration, agreement history and status.
- Keep Finance accounts/EMI schedules and Chitti memberships/contribution schedules/ledgers separate. A person may have either or both.
- Record cash and UPI receipts against the correct account/member and due period; retain payment/reversal history, prevent duplicate retries, update balances and provide printable receipts.
- Show expected/paid/outstanding/lifted and agreement information inline in the Members tab while retaining detailed member views.
- Provide reports for date-range collection, outstanding/overdue, Finance, Chitti, collector and payment method, with CSV, Excel and printable PDF output derived from the displayed data.
- Apply Aadhya identity, AMF logo and Vayu attribution; the supplied business banner provides address, CIN and phone values used on printable documents.
- WhatsApp is requested, but no provider, account, approved message templates, consent or delivery policy is confirmed in source.
- Never infer financial or legal contract terms that have not been approved.

The attached PCR/task document identifies BUG-002, BUG-003, BUG-005, BUG-008/009 and reporting as open/â€œNot implementedâ€ at the time of the document, while BUG-001, BUG-004, BUG-006/007 and PCR-001 were marked completed in its status column. The current checkout differs: substantial code now exists for those areas, verified below. The PDF also explicitly requires a two-page A4 agreement and legal/business content review; current browser print preview does not meet that deliverable. Source: `Vayu Integrated Services - Aadhya Micro Finance.pdf`.

## C. Technical architecture

- Backend: FastAPI, async SQLAlchemy, Pydantic schemas, JWT authentication/role permissions, PostgreSQL.
- Web: Next.js 14 App Router, React, TypeScript, Tailwind; client API services call `/api/v1`.
- Main domains/models: users/roles and audit logs; customers; Finance accounts and installment schedules; Chitti plans and Chitti instances; Chitti members and agreements; member contribution rows and period schedules; payouts; independent Finance payment and Chitti transaction ledgers.
- No database schema or migration changes were made in this local implementation/verification cycle.
- Reports are read from both ledgers. Finance account and Chitti contribution transactions are not merged into one posting ledger.
- Payment receipt and report PDF are browser print/save flows. The backend currently generates CSV/XLSX reports, not persisted PDF/receipt artifacts.

## D. Current implementation status by module

| Module | Verified implementation state | API/database/UI/test status |
|---|---|---|
| Authentication/users | Login/JWT and role/permission checks exist. User/admin screens exist. | Backend API and DB models present; auth tests are in the passing suite. No UI browser smoke test performed. |
| Customers/members | CRUD and normalized-digit duplicate mobile validation; Chitti enrollment is unique per Chitti and supports reusing cancelled/rejected membership rows. | Customer APIs/repository/DB present; customer and Chitti duplicate/capacity tests pass. |
| Finance | Finance accounts and installment schedules; payment is tied to an owned Finance schedule, partial schedule payments supported, reversals append ledger rows and restore dues. | Finance/payments APIs and DB present. Payment balance/reversal/report regression passes. Finance partial-payment policy is not persisted/configurable. |
| Chitti plans and creation | Saved-plan workflow plus direct preview/create. Fixed, lift-based, variable/custom schedule configuration is represented in existing snapshots. | Plan/Chitti APIs and DB present; direct create/UI compile. Financial variants not all covered by current regression tests. |
| Chitti lifecycle | Readiness guard checks membership, confirmed agreements and period schedules. Agreement confirmation activates the member only; a separate explicit Start action transitions an eligible DRAFT/UPCOMING Chitti to RUNNING. | Focused API flow test verifies confirmation leaves DRAFT ready, manual Start persists RUNNING, and member/period schedules are not duplicated. Detail UI exposes Start for DRAFT and UPCOMING; lint passed. |
| Agreements | Snapshot-backed generate/print/confirm and status/history. Confirmation creates missing per-member contributions idempotently. | Agreement APIs and DB models present. Generateâ†’Printâ†’Confirm lifecycle and last-confirm activation tested. Current print view is not an approved/persisted two-page A4 PDF. |
| Chitti collections | Collect Payment eligibility returns Finance accounts and active memberships separately. Chitti contribution endpoint enforces configured partial-payment rule, idempotency, schedule/member balance updates and reversals. | Backend regressions exercise a member with no Finance account, partial contribution, retry, key mismatch, reversal, restored balance and audit event. UI uses separate selection/recording path; not browser tested. |
| Finance payments/receipts | Schedule-allocated cash/UPI collection, duplicate idempotency rejection, reversals, accounting and audit rows. Receipt shown after save and can be printed. | Backend payment reversal/idempotency/accounting tests pass. Receipt markup/source audited; physical browser print not exercised and no durable receipt file/record exists. |
| Collections/dashboard | Date-bounded aggregation over Finance and Chitti sources, separate totals and pending details; Collections route/API retained but normal sidebar entry removed. | Historical and current service code present. Relevant report parity/reversal cases pass; full screen-to-screen live comparison not browser tested. |
| Chitti Members tab (PCR-001) | Inline member number/customer code/phone/status, paid/outstanding/expected/lifted, agreement number/status/generated/printed dates, lifecycle actions, expandable installment history; separate member detail remains. | API returns member/agreement/financial fields; component source was compared to supplied screenshot and PCR fields. Desktop table and mobile card code are present. Runtime visual/responsive acceptance not performed in a browser. |
| Reports/exports | Range report data for daily/weekly/monthly, outstanding/overdue, Finance/Chitti, plus collector/payment-method breakdown. CSV/XLSX and browser-print PDF use the report payload. | JSON, CSV, XLSX transaction/summary parity and collector CSV breakdown tests pass. Printable PDF is source-verified as the same rendered data, not generated/opened in a browser. Range date/type rules still need business acceptance. |
| Branding | Shared AMF logo/brand lockup on login/sidebar/header; legal company name on login and printable agreement; Aadhya short name and Vayu attribution in app chrome; address/CIN/phones/Vayu on agreement, receipt and report print headers; browser title updated. | Source and frontend build verified. Address is included in printable documents, not login/sidebar/header. Exact legal authorization of banner details on receipts/contracts remains client confirmation. |
| WhatsApp | Navigation/screen exists. No sending API/service/provider integration found. | Not implemented beyond UI shell; no backend, DB integration or tests. |
| Payouts/winner selection | Payout record/listing and scheduled/custom rule data are present. Automated winner selection, payout release controls and all auction/discount semantics are not verified as complete. | APIs and models exist; dedicated end-to-end payout tests were not run. Auction/fee rules remain unresolved. |
| Audit logs | Audit service and model exist; Finance and Chitti reversal event creation verified by database-backed assertions. | No separate UI runtime acceptance. |
| Mobile/background jobs | README describes mobile/Redis/Celery, but no corresponding mobile/worker package appears in current repository. | Not part of current implemented checkout; do not treat README roadmap as delivered. |

## E. Database and API reference

No schema migration was needed or added. Major data boundaries:

- `customers` â†’ customer identity/contact data.
- `finance_accounts` â†’ `finance_schedules` â†’ immutable `payment_transactions` (including reversal transaction rows).
- `chitti_plans` â†’ `chittis` â†’ `chitti_members` â†’ `chitti_agreements`.
- `chitti_members` â†’ `chitti_member_contributions` (period/member expected, paid and remaining) and `chitti_period_schedule` (Chitti-level period projection).
- `chitti_payouts` stores payout records; `chitti_transactions` stores contribution/payout/reversal ledger events.
- `audit_logs` records mutating actions.

Relevant endpoint families under `/api/v1`:

- `/auth/*`, `/users/*`, `/customers/*`.
- `/finance/*` and `/payments/*`; Finance receipt collection posts to `/payments/`, reversal to `/payments/{payment_id}/reverse`.
- `/payments/customer/{customer_id}/eligible-accounts` returns `finance_accounts` and `chitti_memberships` as separate collections.
- `/chitti/plans/*`, `/chitti/`, `/chitti/{id}`, `/chitti/{id}/activation`, `/start`, `/members`, `/members/{member_id}/agreement/{generate|print|confirm}`, `/contributions`, `/transactions/{transaction_id}/reverse`, `/payouts`.
- `/reports/daily`, `/reports/daily/summary`, `/reports/range`, `/reports/range/export` (`csv` or `xlsx`), `/reports/chitti-plans/{plan_id}/metrics`.

Finance collection requires `finance_account_id` and `finance_schedule_id`; Chitti contributions must use the Chitti contribution endpoint. Idempotency keys prevent retry double-posting. Agreement confirmation activates the member but does not start the Chitti; an operator must use the explicit Start action after the canonical readiness guard returns eligible. Adding additional members after RUNNING remains disallowed, so enroll intended members before manual start.

## F. Completed and verified in this cycle

- A separate PostgreSQL cluster exists under `C:\Users\ak8a6\AppData\Local\AadhyaMicroFinance\postgres-test-cluster-20261114`, listening on `127.0.0.1:55432`, distinct from the configured development database on port 5432.
- The existing `aadhya_micro_finance_test` contains business/test records and was not used by destructive fixtures in this verification. The destructive fixture was run only against the newly created, initially empty `aadhya_micro_finance_lift_20261114_test` on port 55432. Its identity and zero-table state were independently verified immediately before tests.
- The fixture in `backend/tests/conftest.py` explicitly requires a `*_test` database and rejects the configured development target. No development or production database was connected to, dropped or reset.
- For the critical payment report, the existing screenshot Chitti and its two â‚¹100 ledger rows were read under a read-only transaction from `aadhya_micro_finance_test`; no records were edited, added, reversed or recreated.
- Agreement confirmation previously auto-started an eligible Chitti. The Manual Chitti Start Workflow addendum below supersedes that behavior: confirmation now leaves lifecycle status unchanged and operators must use the explicit Start action.
- Corrected Finance balance calculation to exclude the reversed original and avoid netting the reversal twice. Daily report now excludes the reversed original receipt from completed collections and reports the reversal separately.
- Added Collector/Payment Method grouped summary (per-label Finance/Chitti/combined totals and count) and included it in displayed report state, CSV and Excel.
- Added safe regression assertions for agreement auto-start and schedule counts, Finance idempotency/reversal/audit, Chitti eligibility without Finance, partial payment/retry/key mismatch/reversal/audit, CSV/XLSX parity and collector breakdown.
- Fixed the reported Chitti payment visibility/progress defect: Payments API now reads a combined history projection from the separate Finance and Chitti ledgers; Chitti contribution writes synchronize period aggregates/state and current-period progress; read APIs calculate accurate legacy schedule state without rewriting financial rows. Payment details/receipt view is available from Payments.
- Implemented the user-approved lift surcharge for daily, weekly and monthly schedules: 1% of original Chitti value starts the period after lift and ends at the original final period; legacy plan snapshots retain their saved pre/post amounts.
- Adjusted the login lockup so â€œPowered by Vayu Integration Servicesâ€ is directly beneath the legal company name, consistent with PCR-002.
- No push, deployment, production access, business-record edit, or schema change.

## G. Pending or partial work

1. Final approved two-page A4 agreement output (including KYC/nominee handling, declarations, winner/payout clauses, signature blocks/page breaks) is not implemented as an approved durable PDF. Current preview is browser-print content; legal/business copy needs client approval first.
2. WhatsApp sending needs provider/account, template, consent/opt-out, delivery and failure-handling decisions; screen alone is not integration.
3. Payout/winner workflow, especially auction winner selection, discounts, commissions/fees, reserve and payout approval, needs client-approved financial semantics and end-to-end regression.
4. PDF output is browser Print/Save, not a server-generated artifact. Receipt is also browser-print only and is not persisted.
5. Finance partial-payment allowance has no account-level policy setting. Confirm whether all Finance schedules allow partial collection or require configurable policy.
6. PCR-001 source and supplied screenshot were reviewed; authenticated browser visual/responsive acceptance remains pending because the Windows browser-control helper failed.
7. Branding source/build and static asset requests are verified; screenshot-level visual rendering and legal authorization of printed address/CIN/phone remain unverified.
8. No frontend test runner/script exists. Payment/authenticated workflows were covered by backend tests and HTTP probes, but not visually exercised in an authenticated browser.

## H. Known bug and requirement tracker

| ID / issue | Current assessment | Evidence and residual risk |
|---|---|---|
| BUG-001 Dashboard member count = 0 | FIXED; backend regression passes | Enrolled count is distinct from active count; dashboard/summary/member list assertions pass. |
| BUG-002 duplicate member registration | FIXED; covered | Per-Chitti duplicate and capacity/re-enrolment tests pass; customer duplicate validation tests pass. No production concurrency/race test. |
| BUG-003 Start Chitti warning/no progress | FIXED; covered | Readiness blockers and failed start persistence tested; canonical transition used for auto-start. |
| BUG-004 remains Draft after Start | FIXED; covered | Manual Start persists RUNNING; agreement confirmation alone leaves an eligible Chitti ready in DRAFT/UPCOMING. Focused regression covers both transitions and schedule counts. |
| Agreement PDF/content | PARTIAL / not accepted | Dynamic preview exists, but no approved, complete two-page A4 PDF; legal clauses and print layout need approval. |
| BUG-005 Chitti collection depends on Finance account | FIXED in API flow; test covered | Customer with Chitti membership and no Finance account receives separate Chitti eligibility and can post a contribution. Receipt is browser printable. |
| BUG-006 Dashboard vs Collections totals mismatch | FIXED in backend aggregation paths; regression covered in part | Date-based two-ledger totals/reversal behavior tested; UI runtime parity was not browser verified. |
| BUG-007 Finance/Chitti shown separately | FIXED in report data/UI source | Source fields and separate pending/collection sections exist; report integration tests pass. |
| BUG-008 Generate status refresh | FIXED in source; API workflow covered | Member panel refreshes data after success. No browser interaction test. |
| BUG-009 Print/Confirm status refresh | FIXED in source; API workflow covered | Member panel refreshes data after success. No actual printer/browser print test. |
| PCR-001 inline member information | IMPLEMENTED in source; visual acceptance PARTIAL | Desktop table/mobile cards expose required data and action states; separate detail retained. No runtime screenshot at target viewport. |
| PCR-002 branding | IMPLEMENTED per stated login/header title/Vayu requirements; source/build verified | Printable document headers include banner business details. Address not displayed in app chrome. Runtime visual acceptance pending. |
| Collect Payment membership selector | IMPLEMENTED; API case tested | Eligible Finance and Chitti records are separate; member with no Finance account is covered. Multiple-running-Chitti visual selection not browser tested. |
| Payment allocation/outstanding/ledger | Backend-covered for key paths | Finance schedule allocation, partial due, duplicate idempotency, reversal restoration, Chitti contribution partial/idempotency/reversal, and audit rows tested. Concurrency/race behavior not verified. |
| Critical Chitti payment history/schedule/progress report | FIXED; 2-member regression passes | Root cause: Payments list queried only `payment_transactions` while Chitti writes were persisted in `chitti_transactions`; contribution writes updated member/schedule amounts but did not sync saved period status/current-period progress. The screenshotâ€™s two â‚¹100 transactions already existed, so no reconciliation or duplicate posting was done. |
| Local UI plain/unresponsive login | ROOT CAUSE FOUND; isolated local instance serves assets and API | `next dev` and `next build` shared `web/.next`; the still-running dev process emitted CSS/JS URLs returning 404 after the build. Its client defaulted to `/api/v1`, rewritten to Docker-only `backend:8000`, which returned 500 on the host. Isolated `NEXT_DIST_DIR`, local `.env.local` API base and port 3001 solve those HTTP failures. Authenticated visual acceptance is still pending. |
| Reports return data/export | IMPLEMENTED; JSON/CSV/XLSX tested | Export totals/transaction rows are compared to JSON response; Collector grouped CSV is covered. Printable PDF is only source-level verified. |
| WhatsApp notifications | NOT IMPLEMENTED | UI route only; no sender/provider/API found. |

## I. Previous decisions and unresolved questions

Verified existing choices: Finance and Chitti ledgers stay separate; a retry with the same Chitti key/amount/member/period returns the existing result; a reused key with different request content is rejected; Finance duplicate key is rejected; reversal appends a ledger/audit row and restores the due; Chitti cannot start while an enrolled member agreement remains pending; direct Chitti setup preserves an internal plan snapshot for compatibility.

Unresolved client decisions, not inferred here:

- Approve legal agreement clauses and exact two-page A4 layout, disclosure/KYC fields, signatures and digital/physical confirmation meaning.
- Confirm whether Chitti may start below full seat capacity (current readiness checks all *enrolled* agreements and existing period schedule, not all capacity seats). Members cannot be added after RUNNING.
- Define auction/winner selection, discount/commission/fees, reserves and payout approval/posting rules.
- Define Finance partial-payment policy by product/account and how overpayments/advance credit should work.
- Confirm official address, phone/CIN and whether each may legally appear on agreements and receipts.
- Confirm whether browser-printed receipts/reports are sufficient or durable server-generated PDFs are required.
- Select WhatsApp provider, approved template language, opt-in/opt-out and failure/retry policy.
- Confirm date-window/timezone and business meaning for daily/weekly/monthly, outstanding and overdue reports.

## J. Verification results and next priorities

### Actual verification results (2026-11-14)

- Database safety: `aadhya_micro_finance_lift_20261114_test` was independently verified on port 55432 with zero public tables before destructive fixtures. The current backend process was confirmed through `pg_stat_activity` to use the existing `aadhya_micro_finance_test` on port 55432, not `finance_chitti` on port 5432. This was the intended read-only screenshot dataset; no destructive fixture ran against it.
- Critical payment data: Chitti `b7c01f34-d3de-4446-9ca0-5c86a4eb12c3` (`CHIT-000001`) has two persisted CASH CONTRIBUTION rows, each â‚¹100 for period 1 on 2026-11-14, IDs `007c9c0c-be86-4077-9686-bb02699cf448` and `6161b819-f40d-4433-9041-e98b8df4b0d8`. Period 1 stored expected â‚¹200, collected â‚¹200, pending â‚¹0 but stale `UPCOMING`; Chitti stored `current_period=0`. Read-only inspection confirmed the existing rows; no customer or financial records were changed.
- Backend regressions: **11 focused tests passed** (lift + Chitti flow); **42 full backend tests passed**, with one passlib/argon2 deprecation warning, on the separate empty `aadhya_micro_finance_lift_20261114_test` database.
- Lift rule coverage: all three frequencies, next-period start, fixed non-compounding original-value surcharge, schedule end, custom payout order and legacy snapshot compatibility passed. Chitti payout integration verifies member expected/outstanding/collection/report changes.
- Frontend lint: passed with two existing `react-hooks/exhaustive-deps` warnings in Plans and Customers. TypeScript check: passed after Next's local type include update.
- Production frontend build: passed in the previous verification run (22 routes); running it against the same `.next` as an active Next dev server caused the runtime asset mismatch below. A second production build was not run while preserving the active development servers.
- UI root cause: the active process on port 3000 is `next dev`, while its shared `web/.next` was overwritten by `next build`; the served login HTML then referenced CSS and JS assets returning 404. Tailwind directives/config, PostCSS, root layout CSS import and brand assets are present. Separately, no `web/.env.local` existed, so the client used relative `/api/v1`; the Next rewrite targets Docker service `backend:8000`, producing HTTP 500 on this Windows host.
- Local runtime stabilization: added an environment-selectable Next `distDir`, local-only `web/.env.local` pointing the client at `http://127.0.0.1:8000/api/v1`, and a gitignore entry for the verification output. Started a separate Next dev instance at port 3001 using `.next-stabilization`, leaving the pre-existing port-3000 process untouched. On port 3001 `/login` returned 200; its CSS and referenced JS assets returned 200; direct unauthenticated `/auth/me` returned the expected 403 with CORS allowing `http://localhost:3001`; a deliberately nonexistent test username reached the login endpoint and returned the expected 401 instead of a frontend proxy 500. These are HTTP/runtime checks, not visual acceptance.
- Browser visual verification: **NOT COMPLETED**. The computer-use helper failed during Windows setup twice; the alternate browser launch was blocked by host policy. No screenshot or computed-style observation was obtained. The authenticated application screens, real-credential login, desktop/mobile appearance, payment receipt, refresh behavior, and reports were therefore not marked visually verified.
- `git diff --check`: passed. No push, deployment, schema changes, or production access occurred.

### Exact next development task

Payment synchronization, schedule/payout projection, and the approved lift calculation are implemented and regression-tested. Browser visual acceptance is the immediate next verification task at `http://localhost:3002` (valid credentials/session have not been verified on that separate local port). Afterward, the next product task is the agreement deliverable: confirm legal/business agreement wording and required fields, then produce the final two-page A4 print/PDF layout and visually verify Generate â†’ Print â†’ Confirm. Do not invent legal clauses. WhatsApp and auction/winner payout behavior remain blocked on the client decisions in section I.

### Addendum â€” schedule, payout projection, and Chitti plan choices (2026-11-14)

- Resolved the newly reported â€œpaid period still UPCOMING / Chitti at period 0â€ behavior in the effective schedule read model: read-time status now reflects paid/partial/due/overdue/future state and summary progress counts contiguous completed periods. This is a projection from persisted ledger and schedule data; it does not rewrite the previously displayed test records.
- Added payout projections to that same read model for saved `SCHEDULED` and `CUSTOM` payout rules, deriving recipient, expected net, and fee from the existing calculation engine and period expected collection. The Chitti detail page now separates these projections from actual posted payouts; an empty actual payout list remains accurate until an authorized payout is recorded. No payout was recorded as part of this fix, and no unapproved auction estimate was invented.
- The New Chitti direct form now defaults to the two approved contribution plan choices, Fixed and Lift-based. Existing saved plans remain an optional workflow and historical records are untouched; incompatible legacy contribution plan types are omitted from its selectable saved-plan list.
- Extended the Chitti regression test for completed/current progress, due-today state, scheduled payout estimates/recipient sequence, and the distinction between projections and actual payouts. `tests/test_chitti_flow.py`: **6 passed** against `aadhya_micro_finance_lift_20261114_test`, independently confirmed at `127.0.0.1:55432`; this disposable database was empty before the destructive fixture.
- Re-ran the complete backend suite after these changes: **42 passed, 1 existing passlib/argon2 deprecation warning**. The disposable test database was independently confirmed as `aadhya_micro_finance_lift_20261114_test` on port 55432 with zero public tables before the suite.
- Frontend `npm run lint` and `npx tsc --noEmit`: **passed**. Two pre-existing React hook dependency warnings remain in Chitti Plans and Customers. `git diff --check`: passed.
- The supplied screenshot dataset has two existing â‚¹100 Chitti contributions and no actual payout rows. Prior read-only DB inspection confirmed period 1 collected â‚¹200 against â‚¹200 expected and stale stored `UPCOMING`/progress 0, explaining the display discrepancy. The dataset was not changed.
- The port-3001 application was still connected to the already-running old API process on port 8000, so its stale display did not include these backend changes. A parallel local verification instance was started at **http://localhost:3002**, with backend port 8001. Login and Chitti routes and backend OpenAPI returned HTTP 200; CORS preflight for the new frontend origin succeeded. A separate read-only connection confirmed the parallel APIâ€™s configured target `aadhya_micro_finance_test` on port 55432 and the screenshot data counts (3 customers, 2 Chitti transactions). This is a browser-route/HTTP check, not a logged-in visual acceptance; credentials/session compatibility and screenshot-level verification remain unconfirmed. The parallel API uses the existing local test dataset, never the disposable fixture target; no business row was modified.
- Remaining verification: authenticate on port 3002 and visually confirm that the existing Chitti shows period 1 `COMPLETED`, progress 1/14, due/future statuses by calendar, scheduled member/payout values in Payouts, and the two existing receipts in Payments. Confirm that only Fixed and Lift-based are offered on New Chitti. Actual payout posting still requires an approved business operation, and its calculation/approval semantics remain client-dependent.

### Local change inventory

Backend APIs/services/data/tests changed: `backend/app/api/v1/chitti.py`, `payments.py`, `reports.py`; `backend/app/repositories/customer_repo.py`; `backend/app/schemas/chitti.py`; `backend/app/services/agreement_service.py`, `calculation_engine.py`, `chitti_service.py`, `customer_service.py`, `payment_service.py`, `report_service.py`; `backend/tests/conftest.py`, `test_calculation_engine.py`, `test_chitti_flow.py`, `test_reports_consistency.py`.

Frontend changed: `web/src/app/chitti/[id]/page.tsx`, `chitti/new/page.tsx`, `chitti/plans/new/page.tsx`, `globals.css`, `login/page.tsx`, `payments/collect/page.tsx`, `reports/page.tsx`; `web/src/components/branding/BrandLockup.tsx`, `components/layout/Sidebar.tsx`, `TopBar.tsx`; `web/src/services/chitti.ts`, `payments.ts`, `reports.ts`; `web/public/amf-logo.png`; `web/.eslintrc.json`; local runtime stabilization in `web/next.config.js`, `web/tsconfig.json` (Next-generated type include), `.gitignore`, and ignored `web/.env.local`.

Documentation/user-supplied asset: this tracker and `Vayu Integrated Services - Aadhya Micro Finance.pdf` (the supplied PDF was retained unchanged). Changes are local and unpushed.

### Addendum â€” financial controls, lift management, and input validation (2026-11-15)

#### Implemented

- Chitti contribution collection now locks the member-period row in PostgreSQL before rechecking idempotency and eligibility. It blocks a fully paid period with `CONTRIBUTION_PERIOD_ALREADY_PAID`, blocks future/not-yet-due periods with `CONTRIBUTION_PERIOD_NOT_DUE`, requires the earliest unpaid due period, rejects amounts above remaining balance, and permits partial payments only when the saved Chitti rule explicitly allows them. Same-key retries return the existing transaction; distinct concurrent requests serialize on the locked contribution row.
- Fixed Chitti totals now derive from the shared calculation engine as installment Ã— seats Ã— periods. Saved-plan preview and instance creation accept member-count, contribution amount, period-count, frequency, and original-value overrides; fixed values are calculated server-side, preview is debounced from current inputs, and create independently recalculates. The saved plan and old Chitti snapshots are not updated.
- Lift events are separate from payouts. Added `chitti_lift_events`, a partial unique index allowing only one active lift per Chitti period while retaining reversed history, and GET/POST/reversal APIs. Added the Lift Management tab for eligible period, active member, lift date, event history and reversal. Recording a lift does not create a payout; actual payouts remain on the separate Payouts tab.
- The approved 1% rule is applied from the period after the event through the original final period, based on the immutable original Chitti value, for Daily, Weekly and Monthly frequency. It changes only that member's schedule; lift reversal recomputes the member and aggregate period projection while retaining prior payment rows. Legacy lift snapshots with pre/post fields use the approved 1% formula with their pre-lift amount as the regular base; saved post-lift amounts are superseded by the approved rule.
- Direct and saved-plan Fixed forms show derived totals; previews show expected collection per period and final due date. Server preview and create use the same calculation engine.
- Replaced all remaining native `type="number"` controls in the web source with a shared text-based `NumericInput`: invalid characters are stripped, decimal/integer input modes are supported, caret is maintained, mouse-wheel changes are prevented, and min/max validation is applied without spinner UI. A repository search finds no remaining `type="number"` in `web/src`.

#### Kittu transaction inspection â€” read-only

The existing `aadhya_micro_finance_test` database was queried independently at `127.0.0.1:55432`. The three records remain unchanged. All are for customer/member Kittu (#3), Chitti `Test 1% daily 100`, amount â‚¹100, payment date 2026-11-14, and each allocation shows expected â‚¹100, paid â‚¹100, remaining â‚¹0:

| Transaction ID | Period | UTC created timestamp | Idempotency key |
|---|---:|---|---|
| `bcc64bf4-7940-48c8-97e7-d1861f055e5d` | 1 | 2026-11-14 17:44:03.034267+00:00 | `collect-1794678221313-5dfrursqhyy` |
| `589e8847-5b2f-4770-af5f-664afa120a2f` | 2 | 2026-11-14 17:44:36.259852+00:00 | `collect-1794678263682-v0am1olc9t` |
| `d347c974-927c-430c-ba35-0e1d07957e02` | 3 | 2026-11-14 17:44:46.134569+00:00 | `collect-1794678277924-qfpxz9brz` |

These historic payments were not deleted, reversed, modified, or reconciled. The new period eligibility rule prevents future same-day advancement to periods whose due dates have not arrived.

#### Safety and verification

- Destructive test fixtures ran only against `aadhya_micro_finance_lift_20261114_test` on port 55432. Connection identity was independently checked; the configured development target was `finance_chitti` on port 5432 and was not connected to by the fixtures. The data-bearing `aadhya_micro_finance_test` database was used only for read-only Kittu inspection.
- Migration validation initially found that the dynamic baseline included newly added lift metadata, causing the following revision to create the lift table twice. The baseline now excludes the newer lift table; `alembic upgrade head` succeeded on the disposable `_test` database. It was then applied additively to `aadhya_micro_finance_test` so the new local API could use lift events. Before/after counts matched exactly: customers 3; Finance accounts/schedules/payments 0; Chitti plans 2; Chittis 4; members 5; member contributions 37; period schedules 45; payouts 0; Chitti transactions 9; agreements 5; audit logs 8. The only new application table is `chitti_lift_events`, plus Alembic revision tracking. No customer or financial record changed. PostgreSQL emitted the agreements/members cyclic foreign-key ordering warning; migration completed successfully.
- Final backend regression run: **51 passed**, one existing passlib/argon2 deprecation warning. Coverage includes all five Fixed total formula examples, saved-plan overrides and old-plan preservation, Daily/Weekly/Monthly surcharge, final-period no-surcharge, explicit lift vs payout, lift duplicate/reversal, partial payment, same-period full-payment block, future advance block, retry idempotency, and a two-independent-session concurrent over-collection check.
- Frontend lint and TypeScript checks passed; lint still reports the two existing hook-dependency warnings in Chitti Plans and Customers. The final isolated production build in `web/.next-master-audit` completed successfully for 22 routes after the debounced preview and Lift Management UI changes.
- The new local backend at `http://127.0.0.1:8002` exposes both lift routes in OpenAPI. The separate frontend at `http://localhost:3003` returned HTTP 200 for `/login`, `/chitti/new` and `/payments`; it is configured to call that backend and uses the local test database above. The existing old backend on port 8001 remains untouched. The computer-use helper failed to initialize (`trusted Node process exited unexpectedly; kernel reset`), and no compatible headless browser test package is installed. Therefore visual browser acceptance, actual login, live UI interaction, and numeric keyboard/caret behavior are **not verified**. No claim of visual acceptance is made.
- No deployment or Git push occurred. The only database operation on the data-bearing test database was the additive lift-event migration, verified against unchanged before/after record counts. No customer, Finance, Chitti, payment, schedule, agreement or payout record was changed. No production database was accessed.

### Customer profile payment history (CUS-PAY-HISTORY)

- **Root cause:** Customer Details queried only `payment_transactions`; Chitti contributions are recorded in the separate `chitti_transactions` ledger and linked to customers through `chitti_members`, so they were omitted from this read model.
- **Fix:** Customer ledger API now reads both ledgers independently and combines their transaction rows for display, with source/account/period, customer, status and reversal references. It deduplicates by source and ledger row ID and reports counts plus successful paid total excluding reversed entries. Customer Details renders those fields and the summary. No posting logic or schema changed.
- **Files:** `backend/app/services/customer_service.py`, `backend/tests/test_customer_payment_history.py`, `web/src/app/customers/[id]/page.tsx`, `web/src/types/index.ts`.
- **Verification:** Focused backend tests: **3 passed** on `aadhya_micro_finance_lift_20261114_test` (database identity checked; distinct from configured development target). Customer page ESLint and frontend TypeScript check passed.
- **Kittu read-only verification:** `CUS-000003` Kittu has three unique `CHIT-000004` contributions (periods 1â€“3), each â‚¹100 CASH on 2026-11-14; the updated customer-ledger read model returns all three and â‚¹300 successful paid total. No financial rows were modified. Browser rendering was not exercised in this verification.

### Consolidated authenticated browser-verification pass (2026-11-15)

Verification was performed in a separate local Chrome profile through Chrome DevTools Protocol after the in-app computer-use connector failed to initialize. The signed-in test user was `testadmin`; the credentials `testadmin / testpass123` were present in the existing backend test configuration. No financial/customer records were created, edited, reversed, or deleted.

| Area | Status | Browser evidence / remaining checks |
|---|---|---|
| Login and branding | **Verified (login only)** | Chrome rendered the AMF logo, Aadhya Micro Finance identity and Vayu attribution. Authenticated header/document branding was not comprehensively checked. |
| Dashboard | **Verified** | Authenticated page rendered dashboard content without blank-page/runtime errors. Empty â€œtodayâ€ collection totals corresponded to the selected current date; historical sample rows were dated the prior day. |
| Payments | **Verified** | Authenticated page rendered 12 rows. The three Kittu Chitti entries matched the Customer Payment History transaction IDs, periods, amounts and dates. |
| Customers and Kittu Customer Details â†’ Payment History | **Verified** | Customer list and Kittu profile rendered. The profile showed 3 successful Chitti payments totaling â‚¹300 with transaction IDs, period, CASH method, date and status. |
| Chitti list, New Chitti, detail and plans | **Verified (read-only)** | All pages rendered authenticated content. Direct New Chitti form and preview were exercised without submitting/creating a Chitti. Preview for 3 members Ã— â‚¹100 Ã— 3 daily periods returned â‚¹300 per period and â‚¹900 total with due dates. |
| Chitti schedule, members, payouts and lifts tabs | **Verified (read-only)** | Tabs rendered and their API reads succeeded. Schedule and projected payouts were visible; lift tab showed no recorded lift events. No lift, payout, agreement, pause, completion or cancellation action was submitted. |
| Reports page/data | **Verified (read-only)** | Report for 2026-11-14 through 2026-11-15 rendered backend data: â‚¹1,260 total/Chitti collections, 12 transaction rows, including Kittu's three â‚¹100 rows. |
| Report CSV/XLSX/print exports | **Pending** | Export/download and print output were not exercised in the browser. |
| API target and browser requests | **Verified** | Frontend configuration is `http://127.0.0.1:8002/api/v1`; authenticated browser requests reached that API. Observed page/API reads returned successfully and no console/runtime error was observed in the inspected pages. |
| Agreement generation/print/confirmation and automatic activation | **Pending** | Not exercised because print/confirmation can mutate agreement state. |
| Historical financial display consistency | **Failed / discrepancy observed** | Existing CHIT-000004 data is internally inconsistent across summaries: member rows show paid â‚¹300/â‚¹330/â‚¹230 and outstanding â‚¹0/âˆ’â‚¹30/â‚¹70; summary showed â‚¹860 collected and â‚¹100 pending; schedule period 3 showed â‚¹70 pending. No source records were changed. Investigate calculation/read-model consistency before using these figures for acceptance. |
| Lift calculation acceptance | **Partially verified** | New direct-form preview and lift management UI loaded. No actual lift workflow was submitted. The preview displayed expected payout total â‚¹0 for â€œScheduled by member numberâ€; payout calculation semantics/output need separate verification. |

During the session the browser initially received stale code from the already-running non-reload backend on port 8002, so Customer Details omitted Chitti rows. Restarting that local backend with current repository source made the same read-only profile request return the three existing Kittu rows. The frontend remains on port 3003 and is configured for API port 8002. No schema, customer or financial data was changed as part of browser verification. No push or deployment occurred.

Local test URLs:
- `http://localhost:3003/login`
- `http://localhost:3003/dashboard`
- `http://localhost:3003/payments`
- `http://localhost:3003/customers`
- `http://localhost:3003/customers/9b2972d3-7470-4729-a6d4-2c93cebe0312` â€” Kittu (`CUS-000003`)
- `http://localhost:3003/chitti`
- `http://localhost:3003/chitti/new`
- `http://localhost:3003/chitti/2aa47de1-9c77-4786-9490-08cbafc6a66b` â€” `CHIT-000004`
- `http://localhost:3003/chitti/plans`
- `http://localhost:3003/reports`
- API base: `http://127.0.0.1:8002/api/v1`

#### Final status

- Frontend lint, TypeScript check and isolated production build were rerun after the last UI changes; all completed successfully. The two lint hook-dependency warnings remain.
- `git diff --check` passed, and source search found no native number controls.
- The authenticated Chrome verification recorded above supersedes earlier notes that browser interaction was entirely pending. Visual browser checks passed for the listed authenticated pages, subject to explicitly pending export, agreement mutation, keyboard/caret, and financial-consistency checks.

### Manual Chitti Start Workflow (2026-11-15)

- **Approved behavior:** confirming an agreement activates that member but does not start the Chitti. The Chitti remains in its existing DRAFT/UPCOMING state until an operator explicitly selects Start. The existing readiness guard remains authoritative; Start is blocked until enrolled members have confirmed agreements and required period schedules exist.
- **Implementation:** removed the automatic RUNNING transition from agreement confirmation while retaining response compatibility (`chitti_auto_started: false`, `chitti_status` reports the unchanged status). The detail page now shows Start for eligible DRAFT and UPCOMING states and explains that agreement confirmation does not start the Chitti. The existing canonical start endpoint continues to create/synchronize schedules and audit the explicit transition.
- **Regression coverage:** the Chitti lifecycle test verifies the last confirmation leaves status DRAFT and readiness true, an explicit `/start` changes it to RUNNING, and the contribution and period schedule counts remain stable. The report-test setup helper was updated to manually start its fixture Chitti after agreement confirmation.
- **Verification:** `tests/test_chitti_flow.py::test_member_count_duplicate_and_activation` passed (1 passed; existing passlib/argon2 deprecation warning) against `aadhya_micro_finance_lift_20261114_test` at `127.0.0.1:55432`, independently identified and distinct from configured `finance_chitti` on port 5432. Targeted ESLint passed for `web/src/app/chitti/[id]/page.tsx`. No production or customer/financial records were touched.
- **CHIT-000005 read-only inspection:** the existing row is RUNNING, has 9 of 10 seats enrolled, all 9 enrolled members active with confirmed agreements, and 10 schedule periods. It was inspected in a `READ ONLY` transaction on `aadhya_micro_finance_test` at port 55432 and not modified. It is already started, so it did not require any workflow action.
- **Files changed for this workflow:** `backend/app/services/agreement_service.py`, `backend/tests/test_chitti_flow.py`, `backend/tests/test_reports_consistency.py` (fixture setup now performs explicit manual start), `web/src/app/chitti/[id]/page.tsx`, and this tracker.
- **Remaining check:** authenticated visual interaction of the agreement-confirm â†’ readiness â†’ manual Start workflow was not repeated in the browser in this task. The focused API regression and targeted frontend lint passed; no push/deployment occurred.

### Pending Payments and Quick Collect (2026-11-15)

- **Implementation:** Added a read-only pending-payment aggregate for currently due Finance installments and Chitti contribution periods, with source/customer/account identifiers, due date, expected and outstanding amounts, and status. Collect Payment now loads the list on page open, retains customer search, and provides loading/error/empty/refresh states. A Collect action opens the existing manual payment workflow with the selected source and unpaid period preselected and the outstanding amount filled; it never records a payment automatically. Successful manual collection refreshes the list.
- **Business/data safety:** Pending rows are deduplicated by their source schedule/contribution record, future periods and settled/reversed entries are excluded, and existing partial balances are used. Finance and Chitti records remain in their separate ledgers; the endpoint is read-only. Browser verification did not submit payment, and no existing customer or financial records were created or changed.
- **Files changed for this task:** `backend/app/api/v1/payments.py`, `backend/app/services/payment_service.py`, `backend/tests/test_pending_payment_collection.py`, `web/src/services/payments.ts`, `web/src/app/payments/collect/page.tsx`, and this tracker.
- **Verification:** Focused backend regression: `tests/test_pending_payment_collection.py` **passed (1 test)** against the isolated test DB. Targeted ESLint for the Collect Payment page and payment service **passed**. Frontend `npx tsc --noEmit` **passed** after using an ES target-compatible deduplication expression. `git diff --check` **passed**. No frontend test suite was configured for this focused feature.
- **Authenticated Chrome verification:** The current local app rendered `/payments/collect` for the signed-in test account and displayed 14 due records with customer, customer ID/mobile, Chitti/account, period, due date, expected/outstanding amount, and status. Selecting Kittu's CHIT-000006 row opened the existing Record Payment step for contribution period 1, due 15 Nov 2026, with â‚¹1,000 outstanding and the amount prefilled to â‚¹1,000. Cash/UPI selection and the manual Save button were visible. Save was not clicked. No payment was submitted. Chrome was run in a separate local profile through DevTools Protocol because the in-app browser connector was unavailable.
- **Local environment:** Frontend: `http://localhost:3003`; API base: `http://127.0.0.1:8002/api/v1`. The frontend bundle is configured for port 8002; backend health and the pending endpoint were available during verification.
- **Remaining:** Browser verification covered the due-list and one Chitti quick-collect handoff; no Finance Quick Collect handoff or successful-payment refresh was exercised, to avoid recording payments. Existing records on CHIT-000005 were only displayed as due rows in the list; no action was taken on them. No push or deployment occurred.

#### Pending Payments list organization and bounded scrolling (2026-11-15)

- **Change:** Pending rows are now grouped chronologically by due date (oldest first), then by Finance account or Chitti. Added an in-list filter for customer name/ID/mobile and account/Chitti identifiers, with a matching-record count. The pending list has its own bounded 65vh scroll region so a large due list can be browsed without making the whole page excessively long. The existing customer search and payment collection flow retain their compact width and behavior.
- **Browser check:** Authenticated Chrome rendered 14 due records in `/payments/collect`, grouped under one due date and three account/Chitti groups. The list container measured 457px high with 1,882px of content and computed `overflow-y: auto`; page had no application error. This verifies bounded list scrolling on the available sample data; 100+ records were not present to test at production scale.
- **Checks:** Collect Payment page ESLint passed; frontend `npx tsc --noEmit` passed; `git diff --check` passed. No payment action was submitted and no customer/financial record was changed.

## Chitti Release Preparation (2026-11-20)
- Backup: C:\Users\ak8a6\AppData\Local\Temp\kilo\aadhya_backup_20261120_121048 + aadhya_repo.bundle
- Migrations: 0001-0005 linear single head.
- Tests: flow 10/10; lift+constraints 40/40; reports 35/35; frontend tsc exit 0.
- Status: conditionally ready; awaiting commit approval.
