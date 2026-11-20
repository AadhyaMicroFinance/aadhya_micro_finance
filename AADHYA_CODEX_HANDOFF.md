# Aadhya Micro Finance / FinChitti — Codex Handoff

**Purpose:** Continue the existing Aadhya Chitti engineering work without repeating completed audits, duplicating checks, or restarting from scratch.

**Project:** Aadhya Micro Finance / FinChitti  
**Repository:** `D:\Naveen\aadhya_micro_finance`  
**Stack:** Next.js frontend, FastAPI backend, SQLAlchemy async, PostgreSQL, Alembic  
**Client:** Shravan / Aadhya Micro Finance Pvt Ltd

---

## 1. How to use this handoff

This file is the working context and decision record. Read it once, then continue from the current repository state.

### Non-negotiable workflow
- Do not repeat the completed full architecture audit or produce another generic audit report.
- Do not rerun checks that have already been completed unless a specific new code change makes the check necessary, or the prior result is unavailable/invalid.
- Do not create duplicate tests, migrations, models, services, allocation mechanisms, ledgers, or documentation if equivalent functionality already exists.
- Before adding anything, use the existing audit findings below and map each requirement to the current implementation. Inspect only the specific code needed to implement safely.
- If Copilot is still running or editing the working tree, do not work concurrently. Wait for it to finish or stop it cleanly, review its final changes, and then take over. Never allow Copilot and Codex to edit the same repository simultaneously.
- Preserve all current user changes, including uncommitted and untracked files.
- Do not reset, clean, stash, checkout over, or overwrite user work.
- Do not commit, push, deploy, or run production operations.
- Never connect to or modify production or development databases.
- Do not run migrations until the isolated test database endpoint and server identity have been verified.
- Do not fabricate historical financial data or backfill inferred payment allocations.
- Do not modify payout eligibility rules as part of the collection-engine task.
- If a genuine business rule is missing, ask one concise question instead of inventing it.

### Required working style
Implement incrementally in the existing architecture. Do not stop after producing a plan if the code and requirements are sufficiently clear. Report only actual blockers. Do not claim tests passed unless they were run and passed.

---

## 2. Product context and scope boundaries

Aadhya has two business areas:
- **Chitti:** existing application, currently the priority.
- **Finance:** separate future module; not part of this task.

Do not divert into Finance AutoPay, Razorpay, WhatsApp integration, unrelated UI redesign, or new modules. The current goal is to complete and stabilize the Chitti collection engine.

Chitti templates:
- Fixed Chitti.
- Lift-based Chitti.

Supported frequencies:
- Daily.
- Weekly.
- Monthly.

Existing Lift rule:
- Regular contribution plus 1% of the original total Chitti value from the period after lifting, as implemented in the approved existing calculation engine.
- Preserve the existing calculation engine and its semantics. Do not invent or simplify formulas.

Existing records and customer history must be preserved. The client was advised to create fresh Chittis rather than backdate historical Chittis. Do not delete or alter existing Chittis or fabricate past payments.

---

## 3. Existing repository / Git / backup context

- Repository: `D:\Naveen\aadhya_micro_finance`
- Local backup: `E:\aadhya_micro_finance` — preserve it; do not overwrite.
- Branch: `main`.
- Last recorded HEAD: `08978e7` — `Add Chitti financial database constraints`.
- Prior local commits:
  - `caa9c9a` — Harden Chitti contribution payout and lift integrity.
  - `ee8e380` — Fix Chitti lift period synchronization.
  - `08978e7` — Add Chitti financial database constraints.
- Last recorded branch state was 3 commits ahead of `origin/main` (`origin/main` at `666f86b`).
- Last recorded status: no staged changes; P0.5 tracked changes unstaged, plus untracked implementation files.
- These are historical observations, not guaranteed current state. Do not rerun a broad audit. Check `git status` once at takeover only to protect the current work and establish what Copilot changed since the prior snapshot.

Previously recorded untracked items:
- `backend/alembic/versions/0004_chitti_financial_links.py`
- `backend/app/services/chitti_financial_values.py`
- `Vayu Integrated Services - Aadhya Micro Finance.pdf`
- `backend/.venv-test/`

Never commit `.venv-test` or the PDF unless explicitly requested.

Test environment previously recorded:
- venv: `backend\.venv-test`
- Python 3.12.10
- isolated test DB expected: `finance_chitti_test`, host `127.0.0.1`, port `5434`, user `postgres`
- expected container: `aadhya-test-postgres`

Important: the test harness has a destructive migration reset that drops the `public` schema with CASCADE. Its prior guard checked a `*_test` database name and rejected the exact development URL but did not strictly allowlist host/port or verify server identity. Do not run DB-backed tests or migrations until the exact isolated endpoint is verified. Development DB `finance_chitti` is on port `5432`; never use it. A historical audit clone on port `55432` was previously unavailable; do not assume it exists.

---

## 4. Work already completed before the current collection task

### P0.1 — Contribution reversal integrity
Prior work included:
- Chitti-first lock hierarchy.
- Row locks on Chitti, original transaction, member-period contribution, and period schedule.
- Reversal idempotency key based on `reversal-{original.id}`.
- Contribution recording also locks Chitti first.
- Related writes use one transaction.

### P0.2 — Payout integrity improvements
Prior work included:
- Locks on Chitti, period and payout row.
- Prevent duplicate `(chitti, member, period)` payout.
- Optional API idempotency key and deterministic fallback.
- Validate finite, nonnegative amounts and `net = gross - discount - fee`.
- Payout, period, ledger and audit writes in one transaction.

**Separate unresolved finding:** payout service still allowed payout creation without sufficiently enforcing Chitti lifecycle, member eligibility, payout timing, approved amount/available funds. This is a P0 business-policy blocker. Do not alter payout eligibility in the current collection task. It requires a separate confirmed client policy.

### P0.3 — Lift concurrency/integrity
Prior work included:
- Chitti-first locking.
- Locks for Lift event, member, period schedule and member-period contributions.
- Preserve active Lift partial unique index and surcharge rule.
- Removed accidental coupling of `payout_order` with Lift.

### P0.4-A — Lift period pending synchronization
Prior work:
- Historical audit had reported 21 Lift-based period pending/expected mismatches; Fixed Chitti mismatch count 0.
- Member expected/remaining was recalculated but period pending was stale due to different writers.
- `_sync_period_schedules_from_contributions()` was introduced as the single writer for period totals.
- Commit `ee8e380`.

### P0.4-B — Database financial constraints
Prior work:
- 14 named CHECK constraints on contributions, period schedules, payouts and transactions.
- Did not add `paid <= expected` or cross-table arithmetic checks because Lift recalculation can legitimately make paid exceed expected.
- 17 focused tests and full Chitti + constraints suite of 59 tests were reported passed at that time.
- Commit `08978e7`.

### P0.5 — Financial reconciliation and audit integrity (partially implemented)
Prior implementation included:
- Nullable direct reversal reference and payout ledger reference.
- Migration `0004_chitti_financial_links.py`.
- Normal contribution audit logging in same transaction.
- Reversal rows linked to original contribution.
- Payout linked to ledger transaction.
- Effective financial calculation helper `backend/app/services/chitti_financial_values.py`.
- Analytics and report services updated to use effective values.
- Regression and migration tests added.
- Historical records intentionally left NULL/unlinked; no guessed backfill.

Previously recorded P0.5 status:
- B: direct reversal/payout transaction links implemented for new operations; historical links remain NULL.
- C: normal contribution audit implemented for new operations; historical audit rows not backfilled.
- D: report consistency only partial.
- A: historical Lift reconciliation blocked due to lack of verified historical source fixture.
- E: DB-backed/migration verification incomplete.

---

## 5. Latest independent audit findings — use these, do not repeat the audit

The latest read-only engineering audit identified the following. Treat them as known findings; inspect only targeted implementation points when changing code.

### P0 — Unrestricted payout creation
- `record_payout` checked Chitti, member, period number, period schedule, and amount validity/arithmetic.
- It did not adequately require Chitti RUNNING, active member, due period, configured recipient, or amount bounded by approved payout/available funds.
- A DRAFT Chitti with a member and period schedule could accept a very large payout.
- This remains a separate P0 blocker and needs client-approved payout policy. Do not change it during collection-engine implementation.

### P0 — Historical Lift discrepancies unresolved
A prior historical read-only audit reported:
- Member-period ledger vs contribution paid: 0 mismatches.
- Member totals vs contribution aggregates: 0 mismatches.
- Period collection vs member paid: 0 mismatches.
- Period payout vs payout rows: 0 mismatches, but there were 0 payout rows.
- Period pending vs member remaining: 21 mismatches.
- Period expected vs member expected: 21 mismatches.
- All 21 discrepancies were Lift-based; Fixed Chitti mismatches 0.
- Lift events: 2; reversed lifts: 0.
- Contribution ledger entries: 13; matching contribution audit entries: 0.
- Reversal ledger entries: 0; payout ledger entries: 0; payout rows: 0.
- No historical orphan contribution ledger entries.

This result came from a historical audit dataset, not the currently empty `finance_chitti_test` DB. No verified historical fixture is currently available. Do not fabricate the 21 records or repair history blindly. Reconcile only when a verified historical backup/immutable fixture is available.

### P1 — Draft/Upcoming figures inconsistent
- Agreement confirmation can create member contribution rows and activate member while Chitti remains DRAFT.
- `_financial_totals` gives contribution rows precedence over the “not started” fallback.
- Analytics applies financial-status filtering to KPI aggregates but passes all contribution rows into member/pending detail builders.
- A confirmed DRAFT Chitti can therefore show inconsistent expected/pending figures across analytics, summary and daily report.
- Business decision needed: do signed member dues become obligations at agreement confirmation or only when Chitti starts? Do not invent this rule.

### P1 — Negative outstanding in response paths
- Member detail clamps displayed outstanding to zero.
- `_member_to_dict` and summary `get_summary` previously calculated `expected - paid` without a zero floor.
- Lift reversal can reduce expected while paid remains higher.
- Need one approved outstanding definition and consistent tests across member detail/list, period and summary.
- Preserve overpayments; do not destroy money.

### P1 — Migration upgrade path not fully proven
- `0001_baseline_full_schema.py` creates baseline from mutable current ORM metadata.
- Current models already include later financial checks/link fields, so a fresh baseline can create objects before later revisions.
- Existing `0002`/`0003` migration bodies were modified in the worktree; if already applied, changing a revision body does not replay its upgrade.
- Synthetic “older schema” fixture was built from current ORM metadata with selected additions removed; it is not an authoritative pre-P0.5 deployed schema.
- Treat applied migration revisions as immutable. Add forward revisions for new behaviour.
- Downgrade to base is destructive: `0001` drops metadata tables. Never use it as rollback.
- Validate fresh and actual legacy upgrade only on a verified disposable isolated DB.

### P1 — Migration test guard insufficient
- Migration test reset drops `public` schema with CASCADE.
- Prior guard did not strictly allowlist host/port or verify server identity.
- Do not run until strict isolated endpoint verification is implemented and the actual endpoint is verified.

### P2 — Inactive/legacy membership rows
- `record_contribution` and `record_payout` did not validate member status.
- Analytics member loader excludes some statuses but contribution loader may include all contribution rows.
- Policy for retained historical rows needs definition; preserve records.

### P2 — Payout rollback test weakness
- `test_payout_rolls_back_after_controlled_post_mutation_failure` patched transaction repository create, which was the first write. It did not prove rollback after partial payout persistence.
- This is a separate payout-test improvement, not part of current collection task unless collection changes share the relevant transactional path.

---

## 6. Current approved collection business rules

These are explicitly approved by the user. Implement them; do not ask again.

### A. Normal payment
- Payment on time is accepted and allocated to the appropriate contribution period.
- Paid/outstanding/status update immediately.

### B. Partial payments
- A member can make multiple payments against one period.
- Example: expected ₹1,000; payments ₹400 + ₹300 + ₹300 settle it.
- Until fully settled, status is PARTIALLY_PAID.
- Each payment remains a separately traceable transaction.
- Never overwrite previous payments.

### C. Advance payments
- Accept payments before the due date.
- Allocate sequentially to the earliest eligible unpaid contribution periods.
- Example: ₹3,000 at ₹1,000 per period settles three periods.
- Do not alter due dates because a period was paid early.
- Do not make advance payment automatically confer Lift or payout eligibility.

### D. Combined partial + advance payment
- Example: Period 1 expected ₹1,000, Period 2 expected ₹1,000, Period 3 expected ₹1,000; payment ₹1,500.
- Allocate ₹1,000 to Period 1 and ₹500 to Period 2.
- Period 2 remains partially paid with ₹500 outstanding.
- Period 3 remains unpaid.

### E. Excess payment / unallocated member credit
Approved policy:
- If payment exceeds total outstanding across all scheduled periods, retain the excess as unallocated member credit for future adjustment.
- Example: outstanding ₹3,000, payment ₹3,500: allocate ₹3,000 and retain ₹500 as member credit.
- Keep credit separate from period contribution and payout.
- Automatically apply available credit against future eligible contributions.
- Keep complete history of credit creation and utilisation.
- Never silently discard or hide excess.
- Never count unallocated credit as period collection or completed period payment.

### F. Three separate financial concepts
Keep distinct:
1. **Payment received:** actual amount collected.
2. **Period allocation:** portion of a payment applied to a specific period.
3. **Unallocated member credit:** received money not yet allocated to a period.

Do not create a competing second ledger. Reuse/extend the existing transaction and audit architecture. Prefer append-only, traceable credit movements or an equivalent design consistent with current models.

### G. Payment reversal
- Preserve original payment and allocation history.
- Reverse allocation effects through traceable financial entries.
- Correctly reverse credit creation or utilisation related to the payment.
- Recalculate period, member and credit balances.
- Use idempotency and atomic transaction handling.
- Never delete the original transaction.
- Do not invent refund or manual adjustment policies.

### H. Fixed and Lift compatibility
- Preserve existing Fixed and Lift calculation engine.
- Advance allocations must use the effective expected amount for the target period.
- Partial payment and credit adjustment must use the same source of truth.
- Lift/reversal must not erase historical payment allocations.
- If expected amount changes after Lift/reversal, preserve all received money and represent any overpayment as an auditable credit position according to a consistent policy. Do not create or destroy money.
- Do not change payout eligibility.

### I. Reporting
All relevant views must agree:
- Chitti dashboard.
- Member details and history.
- Period collection details.
- Collection reports.
- Outstanding reports.
- Analytics.
- Receipts/transaction history.

Display separately:
- Total received.
- Total allocated.
- Total outstanding.
- Unallocated member credit.

Do not count member credit as period collection. Do not subtract credit twice from outstanding. Displayed outstanding should not be negative, while preserving any overpayment/credit.

---

## 7. Implementation acceptance criteria

Implement against existing code, avoiding duplicate mechanisms.

### Payment/allocation
- Multiple payment records can contribute to one member-period.
- One payment can allocate across multiple member-periods.
- Backend determines allocation; never trust frontend-calculated allocation amounts.
- Define deterministic allocation order: earliest eligible period with outstanding balance first.
- If the existing API accepts a target period, preserve its contract where possible and define how target selection interacts with forward allocation. Do not silently break API consumers.
- Use Decimal/Numeric, not floats.
- Prevent allocation sum from exceeding payment amount.
- Prevent credit spending beyond available balance.
- Use idempotency and consistent locking to prevent double allocation or double spending.
- Payment, allocations, credit movements, member-period updates, ledger and audit must be atomic.

### Statuses
Use existing status conventions if they already express the correct meaning. Do not add duplicate status enums unnecessarily. Required semantics:
- UNPAID: nothing allocated.
- PARTIALLY_PAID: some amount allocated, outstanding remains.
- PAID: current effective expected amount fully covered.
- Future period fully covered in advance: show the existing appropriate paid/advance-paid distinction if supported; otherwise implement a clear compatible representation without changing due date.

### Tests
Add tests only where coverage is missing. Do not duplicate existing tests. At minimum ensure coverage for:
1. Full payment settles period.
2. Partial payment.
3. Multiple partial payments.
4. One payment across multiple periods.
5. Combined current settlement + next-period partial allocation.
6. Excess creates unallocated credit.
7. Credit automatically applied to later eligible period.
8. Partial credit utilisation.
9. No double spending under concurrency.
10. Duplicate payment idempotency.
11. Reversal of payment allocated across multiple periods.
12. Reversal of payment that created credit.
13. Reversal of payment that consumed credit.
14. Lift-based expected amount and surcharge compatibility.
15. Lift reversal preserves received money and allocation history.
16. Rollback after at least one or more writes have occurred.
17. Ledger, allocations, payment received and credit reconcile.

Do not run a DB test until the isolated test DB endpoint and server identity are verified. If not safe/available, run DB-independent tests and report DB tests as blocked, not passed.

---

## 8. Scope order

1. Continue from Copilot's actual final worktree state; do not overwrite or duplicate it.
2. Implement the approved contribution allocation/credit behaviour in the existing architecture.
3. Update reversals and reporting only as required by those changes.
4. Add only missing regression tests.
5. Verify static/unit tests and safe isolated DB tests where possible.
6. Provide a concise implementation report and remaining blockers.

Do not expand this task to resolve the separate payout policy blocker, historical 21 Lift discrepancies, or unrelated migration-history issues unless the collection implementation directly depends on them. Record those separately without diverting the current work.

---

## 9. Required final report

Report:
- Exact files changed.
- Whether any new tables/columns/migrations were necessary and why.
- Payment allocation model.
- Credit accounting model.
- Reversal handling.
- Fixed/Lift compatibility.
- Tests actually run and their exact pass/fail/error counts.
- Whether DB-backed tests and migrations were safely verified.
- Any remaining blocker.

Choose one status:
- **READY FOR INDEPENDENT REVIEW**
- **NOT READY — IMPLEMENTATION ISSUES REMAIN**
- **BLOCKED — REQUIRED SAFE TEST DATABASE OR BUSINESS DECISION MISSING**

Do not claim production-ready based on compilation or unit tests alone.

---

# Single Codex kickoff prompt

Read `AADHYA_CODEX_HANDOFF.md` completely and use it as the authoritative project context and approved business-rule record.

Continue the existing Aadhya Chitti collection-engine work from the current repository state. Do not repeat the completed architecture audit, do not regenerate a generic plan, and do not duplicate existing code, migrations, tests or checks. First establish the current worktree state once so you preserve any changes made by the previous Copilot run. If Copilot is still running, do not edit concurrently; wait until it finishes or is stopped cleanly.

Then map the approved requirements to the existing functions/files briefly and implement the missing functionality only: partial payments, multiple payments per period, sequential advance allocations, unallocated member credit for excess payments, automatic future credit utilisation, safe allocation/payment reversals, Fixed/Lift compatibility, and consistent balances/reports.

All business rules are already approved in the handoff. Do not ask the user to reconfirm them. Do not change payout eligibility. Do not modify production/development databases, run unverified migrations, delete/reset data, commit, push or deploy. Use only the verified isolated test environment; if its server identity cannot be verified, do not run destructive DB tests and report the blocker.

Preserve existing user changes and financial history. Reuse existing architecture and ledger; do not create competing financial systems. Add tests only where existing coverage is missing. Run only checks necessary to validate your changes, and do not claim any test passed unless it actually ran.

Implement incrementally. If a genuinely missing business rule or unsafe dependency prevents a specific operation, stop only that operation, explain the precise blocker, and continue safe work. Finish with the exact files changed, implementation summary, actual test results, migration/DB verification status, and one of the three readiness statuses defined in the handoff.
