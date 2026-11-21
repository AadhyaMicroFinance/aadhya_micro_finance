"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import Pagination from "@/components/ui/Pagination";
import EmptyState from "@/components/ui/EmptyState";
import { CardSkeleton, TableSkeleton } from "@/components/ui/Skeleton";
import { financeApi } from "@/services/finance";
import { paymentsApi } from "@/services/payments";
import { customersApi } from "@/services/customers";
import { useAuthStore } from "@/hooks/useAuth";
import { getApiErrorMessage } from "@/services/api-client";
import { cn, formatCurrency, formatDate, getStatusColor } from "@/lib/utils";
import type {
  Customer,
  DueInfo,
  FinanceCollectionRecord,
  FinanceCollectionsParams,
  FinancePendingCollectionRecord,
  FinanceSchedule,
} from "@/types";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  Clock,
  CreditCard,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

const PER_PAGE = 20;
const PAYMENT_METHODS = ["CASH", "UPI", "BANK_TRANSFER", "OTHER"];

function localDate(): string {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `finance-collection-${crypto.randomUUID()}`;
  }
  return `finance-collection-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function pendingAmount(row: FinancePendingCollectionRecord): number {
  const value =
    row.remaining_amount ??
    row.pending_amount ??
    row.outstanding_amount ??
    row.amount_due ??
    row.expected_amount ??
    0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function scheduleIdOf(row: FinancePendingCollectionRecord): string {
  return String(row.schedule_id || row.finance_schedule_id || row.id || "");
}

function isOverdue(row: FinancePendingCollectionRecord): boolean {
  const status = String(row.status || "").toUpperCase();
  if (status.includes("OVERDUE")) return true;
  if (Number(row.days_overdue || 0) > 0) return true;
  return Boolean(row.due_date && row.due_date < localDate());
}

function methodLabel(method: string | null | undefined): string {
  if (!method) return "—";
  return method
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function StatusPill({ status }: { status: string }) {
  return <span className={cn("badge", getStatusColor(status))}>{status.replace(/_/g, " ")}</span>;
}

function StatCard({
  label,
  value,
  sub,
  icon,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  tone: string;
}) {
  return (
    <div className="card flex items-start gap-3.5">
      <div className={cn("flex-shrink-0 rounded-xl p-2.5", tone)}>{icon}</div>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-surface-400">{label}</p>
        <p className="mt-1 text-xl font-bold tabular-nums text-surface-900">{value}</p>
        <p className="mt-0.5 text-[11px] text-surface-500">{sub}</p>
      </div>
    </div>
  );
}

function PendingTable({
  rows,
  canCollect,
  overdue,
  onRecord,
}: {
  rows: FinancePendingCollectionRecord[];
  canCollect: boolean;
  overdue: boolean;
  onRecord: (row: FinancePendingCollectionRecord) => void;
}) {
  return (
    <div className="table-container">
      <table className="table">
        <thead>
          <tr>
            <th>Customer</th>
            <th>Account</th>
            <th>Installment</th>
            <th>Due date</th>
            <th className="text-right">Pending</th>
            <th>Status</th>
            {canCollect && <th className="text-right">Action</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.id ?? row.schedule_id ?? index)} className={cn(overdue && "bg-danger-50/40")}>
              <td>
                <p className="text-sm font-semibold text-surface-900">{row.customer_name || "—"}</p>
                <p className="text-[11px] text-surface-400">{row.mobile_number || row.customer_id || "—"}</p>
              </td>
              <td className="font-mono text-xs text-surface-600">{row.account_number || "—"}</td>
              <td className="text-xs text-surface-600">
                {row.installment_number ? `#${row.installment_number}` : "—"}
              </td>
              <td className="text-xs text-surface-600">
                {row.due_date ? formatDate(row.due_date) : "—"}
                {Number(row.days_overdue || 0) > 0 && (
                  <span className="mt-0.5 block text-[10px] font-semibold text-danger-600">
                    {row.days_overdue}d late
                  </span>
                )}
              </td>
              <td className="text-right text-sm font-bold tabular-nums text-surface-900">
                {formatCurrency(pendingAmount(row))}
              </td>
              <td><StatusPill status={row.status || (overdue ? "OVERDUE" : "PENDING")} /></td>
              {canCollect && (
                <td className="text-right">
                  <button type="button" onClick={() => onRecord(row)} className="btn-secondary btn-sm">
                    Record
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface RepaymentDraft {
  customer_id: string;
  customer_name: string;
  finance_account_id: string;
  account_number: string;
  finance_schedule_id: string;
  installment_number: number | null;
  amount: string;
  payment_method: string;
  payment_date: string;
  reference_number: string;
  notes: string;
}

function emptyDraft(): RepaymentDraft {
  return {
    customer_id: "",
    customer_name: "",
    finance_account_id: "",
    account_number: "",
    finance_schedule_id: "",
    installment_number: null,
    amount: "",
    payment_method: "CASH",
    payment_date: localDate(),
    reference_number: "",
    notes: "",
  };
}

export default function FinanceCollectionsPage() {
  const permissions = useAuthStore((state) => state.user?.permissions ?? []);
  const canCollect = permissions.includes("payments:create");

  const [pending, setPending] = useState<FinancePendingCollectionRecord[]>([]);
  const [pendingLoading, setPendingLoading] = useState(true);
  const [pendingError, setPendingError] = useState("");

  const [records, setRecords] = useState<FinanceCollectionRecord[]>([]);
  const [meta, setMeta] = useState<{ page: number; per_page: number; total: number; total_pages: number } | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");

  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Pick<FinanceCollectionsParams, "search" | "date_from" | "date_to" | "status">>({
    search: "",
    date_from: "",
    date_to: "",
    status: "",
  });
  const [searchInput, setSearchInput] = useState("");
  const [notice, setNotice] = useState("");

  const [showModal, setShowModal] = useState(false);
  const [draft, setDraft] = useState<RepaymentDraft>(emptyDraft);
  const [eligibleAccounts, setEligibleAccounts] = useState<
    Awaited<ReturnType<typeof paymentsApi.eligibleAccounts>>["finance_accounts"]
  >([]);
  const [schedules, setSchedules] = useState<FinanceSchedule[]>([]);
  const [dueInfo, setDueInfo] = useState<DueInfo | null>(null);
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<Customer[]>([]);
  const [customerLoading, setCustomerLoading] = useState(false);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState("");
  const idempotencyKeyRef = useRef("");
  const eligibleRequestRef = useRef(0);

  const loadPending = useCallback(async () => {
    setPendingLoading(true);
    setPendingError("");
    try {
      setPending(await financeApi.pendingCollections());
    } catch (e) {
      setPending([]);
      setPendingError(getApiErrorMessage(e, "Could not load pending Finance collections."));
    } finally {
      setPendingLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const res = await financeApi.collections({
        page,
        per_page: PER_PAGE,
        search: filters.search || undefined,
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
        status: filters.status || undefined,
      });
      setRecords(res.data ?? []);
      setMeta(res.meta ?? null);
    } catch (e) {
      setRecords([]);
      setMeta(null);
      setHistoryError(getApiErrorMessage(e, "Could not load Finance collection history."));
    } finally {
      setHistoryLoading(false);
    }
  }, [page, filters.search, filters.date_from, filters.date_to, filters.status]);

  useEffect(() => {
    void loadPending();
  }, [loadPending]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters((prev) => (prev.search === searchInput ? prev : { ...prev, search: searchInput }));
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const searchCustomers = useCallback(async (query: string) => {
    if (!query.trim()) {
      setCustomerResults([]);
      setCustomerLoading(false);
      return;
    }
    setCustomerLoading(true);
    try {
      const res = await customersApi.list({ search: query.trim(), status: "ACTIVE", per_page: 10 });
      setCustomerResults(res.data ?? []);
    } catch {
      setCustomerResults([]);
    } finally {
      setCustomerLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!showModal) return;
    const timer = window.setTimeout(() => void searchCustomers(customerQuery), 200);
    return () => window.clearTimeout(timer);
  }, [showModal, customerQuery, searchCustomers]);

  const dueRows = useMemo(() => pending.filter((row) => !isOverdue(row)), [pending]);
  const overdueRows = useMemo(() => pending.filter((row) => isOverdue(row)), [pending]);
  const pendingTotal = useMemo(() => dueRows.reduce((sum, row) => sum + pendingAmount(row), 0), [dueRows]);
  const overdueTotal = useMemo(() => overdueRows.reduce((sum, row) => sum + pendingAmount(row), 0), [overdueRows]);

  const updateFilter = (key: "date_from" | "date_to" | "status", value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const clearFilters = () => {
    setSearchInput("");
    setFilters({ search: "", date_from: "", date_to: "", status: "" });
    setPage(1);
  };

  const loadEligible = async (
    customerId: string,
    preferredAccountId = "",
    preferredScheduleId = ""
  ) => {
    const requestId = ++eligibleRequestRef.current;
    setAccountsLoading(true);
    setModalError("");
    setSchedules([]);
    setDueInfo(null);
    try {
      const eligible = await paymentsApi.eligibleAccounts(customerId);
      if (requestId !== eligibleRequestRef.current) return;
      const accounts = eligible.finance_accounts;
      setEligibleAccounts(accounts);

      const accountId = preferredAccountId || accounts[0]?.id || "";
      if (!accountId) {
        setDraft((prev) =>
          prev
            ? { ...prev, finance_account_id: "", account_number: "", finance_schedule_id: "", amount: "" }
            : prev
        );
        return;
      }

      const selected = accounts.find((account) => account.id === accountId);
      setDraft((prev) =>
        prev
          ? {
              ...prev,
              finance_account_id: accountId,
              account_number: selected?.account_number || prev.account_number,
            }
          : prev
      );

      const [loadedSchedule, loadedDue] = await Promise.all([
        financeApi.getSchedule(accountId),
        paymentsApi.getDue(customerId, accountId).catch(() => null),
      ]);
      if (requestId !== eligibleRequestRef.current) return;

      setSchedules(loadedSchedule);
      setDueInfo(loadedDue);

      const preferred = preferredScheduleId
        ? loadedSchedule.find((item) => item.id === preferredScheduleId)
        : undefined;
      const fallback = loadedSchedule.find(
        (item) => item.remaining_amount > 0 && item.status !== "PAID"
      );
      const chosen = preferred || fallback;
      setDraft((prev) =>
        prev
          ? {
              ...prev,
              finance_schedule_id: chosen?.id || "",
              installment_number: chosen?.installment_number ?? prev.installment_number,
              amount: chosen ? String(chosen.remaining_amount) : prev.amount,
            }
          : prev
      );
    } catch (e) {
      if (requestId !== eligibleRequestRef.current) return;
      setEligibleAccounts([]);
      setModalError(getApiErrorMessage(e, "Could not load eligible Finance accounts."));
    } finally {
      if (requestId === eligibleRequestRef.current) setAccountsLoading(false);
    }
  };

  const openRepayment = (row?: FinancePendingCollectionRecord) => {
    const customerId = String(row?.customer_id || "");
    const accountId = String(row?.finance_account_id || row?.account_id || "");
    const scheduleId = row ? scheduleIdOf(row) : "";
    const amount = row ? pendingAmount(row) : 0;

    idempotencyKeyRef.current = newIdempotencyKey();
    eligibleRequestRef.current += 1;
    setDraft({
      ...emptyDraft(),
      customer_id: customerId,
      customer_name: String(row?.customer_name || ""),
      finance_account_id: accountId,
      account_number: String(row?.account_number || ""),
      finance_schedule_id: scheduleId,
      installment_number: row?.installment_number ?? null,
      amount: amount > 0 ? String(amount) : "",
    });
    setEligibleAccounts([]);
    setSchedules([]);
    setDueInfo(null);
    setCustomerQuery("");
    setCustomerResults([]);
    setModalError("");
    setNotice("");
    setShowModal(true);

    if (customerId) void loadEligible(customerId, accountId, scheduleId);
  };

  const closeModal = () => {
    if (submitting) return;
    eligibleRequestRef.current += 1;
    setShowModal(false);
    setModalError("");
  };

  const selectCustomer = (customer: Customer) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            customer_id: customer.id,
            customer_name: customer.full_name,
            finance_account_id: "",
            account_number: "",
            finance_schedule_id: "",
            installment_number: null,
            amount: "",
          }
        : prev
    );
    setCustomerQuery(customer.full_name);
    setCustomerResults([]);
    void loadEligible(customer.id);
  };

  const selectAccount = (accountId: string) => {
    const account = eligibleAccounts.find((item) => item.id === accountId);
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            finance_account_id: accountId,
            account_number: account?.account_number || "",
            finance_schedule_id: "",
            installment_number: null,
            amount: "",
          }
        : prev
    );
    if (accountId && draft.customer_id) void loadEligible(draft.customer_id, accountId);
  };

  const selectSchedule = (scheduleId: string) => {
    const chosen = schedules.find((item) => item.id === scheduleId);
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            finance_schedule_id: scheduleId,
            installment_number: chosen?.installment_number ?? null,
            amount: chosen ? String(chosen.remaining_amount) : "",
          }
        : prev
    );
  };

  const submitRepayment = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft || submitting) return;
    const amount = Number(draft.amount);

    if (!draft.customer_id || !draft.finance_account_id || !draft.finance_schedule_id) {
      setModalError("Select a customer, Finance account and unpaid installment.");
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setModalError("Enter a repayment amount greater than zero.");
      return;
    }
    if (!draft.payment_date) {
      setModalError("Enter the payment date.");
      return;
    }

    setSubmitting(true);
    setModalError("");
    try {
      await paymentsApi.create({
        customer_id: draft.customer_id,
        finance_account_id: draft.finance_account_id,
        finance_schedule_id: draft.finance_schedule_id,
        amount,
        payment_method: draft.payment_method,
        payment_date: draft.payment_date,
        reference_number: draft.reference_number.trim() || undefined,
        notes: draft.notes.trim() || undefined,
        idempotency_key: idempotencyKeyRef.current || newIdempotencyKey(),
      });
      setShowModal(false);
      setNotice(`Repayment of ${formatCurrency(amount)} recorded.`);
      await Promise.all([loadPending(), loadHistory()]);
    } catch (e) {
      // Keep the same idempotency key on retry so a timed-out request cannot
      // be recorded twice when the user presses Submit again.
      setModalError(getApiErrorMessage(e, "Could not record this repayment."));
    } finally {
      setSubmitting(false);
    }
  };

  const totalPages = Math.max(1, meta?.total_pages ?? 1);

  return (
    <DashboardLayout>
      <div className="space-y-7">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-xl bg-brand-50 p-2 text-brand-600">
                <CircleDollarSign size={18} />
              </span>
              <h1 className="text-xl font-bold tracking-tight text-surface-900 sm:text-2xl">
                Finance Collections
              </h1>
            </div>
            <p className="mt-1.5 text-sm text-surface-500">
              Pending repayments, overdue accounts and Finance-only collection history.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => void Promise.all([loadPending(), loadHistory()])} className="btn-secondary btn-sm">
              <RefreshCw size={14} />
              Refresh
            </button>
            {canCollect && (
              <button type="button" onClick={() => openRepayment()} className="btn-primary btn-sm">
                <Plus size={14} />
                Record repayment
              </button>
            )}
          </div>
        </div>

        {notice && (
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-success-200 bg-success-50 px-4 py-3 text-sm text-success-700">
            <CheckCircle2 size={16} />
            <span className="flex-1">{notice}</span>
            <button type="button" onClick={() => setNotice("")} className="text-success-700 hover:text-success-900">
              <X size={15} />
            </button>
          </div>
        )}

        {historyError && (
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
            <AlertTriangle size={16} />
            <span className="flex-1">{historyError}</span>
            <button type="button" onClick={() => void loadHistory()} className="btn-secondary btn-sm">Retry</button>
          </div>
        )}

        {/* Summary */}
        {pendingLoading && !pending.length ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => <CardSkeleton key={i} />)}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              label="Pending dues"
              value={String(dueRows.length)}
              sub={`${formatCurrency(pendingTotal)} awaiting collection`}
              icon={<Clock size={18} />}
              tone="bg-warning-50 text-warning-600"
            />
            <StatCard
              label="Overdue dues"
              value={String(overdueRows.length)}
              sub={`${formatCurrency(overdueTotal)} past due date`}
              icon={<AlertTriangle size={18} />}
              tone="bg-danger-50 text-danger-600"
            />
            <StatCard
              label="Recorded collections"
              value={String(meta?.total ?? records.length)}
              sub="Finance repayment entries in history"
              icon={<CreditCard size={18} />}
              tone="bg-brand-50 text-brand-600"
            />
          </div>
        )}

        {/* Pending & overdue */}
        <div className="card space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex items-start gap-2.5">
              <span className="rounded-xl bg-warning-50 p-2 text-warning-600"><CalendarClock size={16} /></span>
              <div>
                <h2 className="text-base font-semibold text-surface-900">Pending &amp; Overdue</h2>
                <p className="mt-0.5 text-xs text-surface-500">
                  Installments from Finance accounts only
                </p>
              </div>
            </div>
            {canCollect && (
              <button type="button" onClick={() => openRepayment()} className="btn-secondary btn-sm">
                <Plus size={14} />
                Record repayment
              </button>
            )}
          </div>

          {pendingError && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
              <AlertTriangle size={15} />
              <span className="flex-1">{pendingError}</span>
              <button type="button" onClick={() => void loadPending()} className="btn-secondary btn-sm">Retry</button>
            </div>
          )}

          {pendingLoading && !pending.length ? (
            <TableSkeleton rows={4} cols={7} />
          ) : !pendingError && pending.length === 0 ? (
            <EmptyState
              icon="✅"
              title="Nothing pending"
              description="All Finance installments are fully collected."
            />
          ) : (
            <>
              <div className="space-y-2.5">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-500">
                  Due ({dueRows.length})
                </h3>
                {dueRows.length ? (
                  <PendingTable rows={dueRows} canCollect={canCollect} overdue={false} onRecord={openRepayment} />
                ) : (
                  <EmptyState icon="📅" title="No upcoming dues" description="Nothing is due right now." />
                )}
              </div>

              <div className="space-y-2.5">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-danger-600">
                  Overdue ({overdueRows.length})
                </h3>
                {overdueRows.length ? (
                  <PendingTable rows={overdueRows} canCollect={canCollect} overdue onRecord={openRepayment} />
                ) : (
                  <EmptyState icon="🎉" title="No overdue installments" description="Every account is on schedule." />
                )}
              </div>
            </>
          )}
        </div>

        {/* History */}
        <div className="card space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold text-surface-900">Collection History</h2>
              <p className="mt-0.5 text-xs text-surface-500">
                Recorded Finance repayments only — Chitti contributions never appear here.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="relative lg:col-span-2">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
              <input
                type="search"
                className="input-field py-2 pl-9 text-xs"
                placeholder="Search customer, mobile or account"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </div>
            <div>
              <label className="input-label text-xs">From</label>
              <input
                type="date"
                className="input-field py-2 text-xs"
                value={filters.date_from}
                onChange={(e) => updateFilter("date_from", e.target.value)}
              />
            </div>
            <div>
              <label className="input-label text-xs">To</label>
              <input
                type="date"
                className="input-field py-2 text-xs"
                value={filters.date_to}
                onChange={(e) => updateFilter("date_to", e.target.value)}
              />
            </div>
            <div>
              <label className="input-label text-xs">Status</label>
              <select
                className="input-field py-2 text-xs"
                value={filters.status}
                onChange={(e) => updateFilter("status", e.target.value)}
              >
                <option value="">All statuses</option>
                <option value="COMPLETED">Completed</option>
                <option value="PENDING">Pending</option>
                <option value="FAILED">Failed</option>
                <option value="REVERSED">Reversed</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end">
            <button type="button" onClick={clearFilters} className="btn-ghost btn-sm">
              Clear filters
            </button>
          </div>

          {historyLoading && !records.length ? (
            <TableSkeleton rows={6} cols={8} />
          ) : records.length === 0 ? (
            <EmptyState
              icon="🧾"
              title="No collections found"
              description="Try adjusting the filters, or record a Finance repayment to get started."
            />
          ) : (
            <>
              <div className={cn("table-container", historyLoading && "opacity-60")}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Transaction</th>
                      <th>Customer</th>
                      <th>Account</th>
                      <th>Installment</th>
                      <th>Method</th>
                      <th>Status</th>
                      <th className="text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((record) => (
                      <tr key={record.id} className={cn(record.is_reversal && "bg-danger-50/40")}>
                        <td className="text-xs text-surface-600">
                          {record.payment_date ? formatDate(record.payment_date) : formatDate(record.created_at)}
                        </td>
                        <td className="font-mono text-[11px] text-surface-500">{record.transaction_id}</td>
                        <td>
                          <p className="text-sm font-semibold text-surface-900">{record.customer_name}</p>
                          <p className="text-[11px] text-surface-400">{record.collected_by || "—"}</p>
                        </td>
                        <td className="font-mono text-xs text-surface-600">{record.account_number || "—"}</td>
                        <td className="text-xs text-surface-600">
                          {record.installment_number ? `#${record.installment_number}` : "—"}
                        </td>
                        <td className="text-xs text-surface-600">{methodLabel(record.payment_method)}</td>
                        <td>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <StatusPill status={record.status} />
                            {record.is_reversal && <span className="badge-danger">REVERSAL</span>}
                          </div>
                        </td>
                        <td
                          className={cn(
                            "text-right text-sm font-bold tabular-nums",
                            record.is_reversal ? "text-danger-600" : "text-success-600"
                          )}
                        >
                          {record.is_reversal ? "-" : ""}
                          {formatCurrency(record.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                totalPages={totalPages}
                total={meta?.total}
                perPage={meta?.per_page ?? PER_PAGE}
                onChange={setPage}
                disabled={historyLoading}
              />
            </>
          )}
        </div>
      </div>

      {/* Record repayment modal */}
      {showModal && draft && (
        <div className="modal-backdrop" onClick={closeModal}>
          <div className="modal-content max-w-2xl p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-5 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-surface-900">Record Finance Repayment</h2>
                <p className="mt-1 text-xs text-surface-500">
                  Only Finance accounts and their installments are available here.
                </p>
              </div>
              <button type="button" onClick={closeModal} className="rounded-lg p-2 text-surface-400 hover:bg-surface-100" aria-label="Close">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={submitRepayment} className="space-y-4">
              <div>
                <label className="input-label">Customer</label>
                {draft.customer_id ? (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-brand-100 bg-brand-50 px-3 py-2.5 text-sm">
                    <span className="font-semibold text-brand-800">
                      {draft.customer_name || draft.customer_id}
                    </span>
                    <button
                      type="button"
                      className="text-xs font-semibold text-brand-700 hover:text-brand-800"
                      onClick={() => {
                        eligibleRequestRef.current += 1;
                        setDraft((prev) =>
                          prev
                            ? {
                                ...prev,
                                customer_id: "",
                                customer_name: "",
                                finance_account_id: "",
                                account_number: "",
                                finance_schedule_id: "",
                                amount: "",
                              }
                            : prev
                        );
                        setEligibleAccounts([]);
                        setSchedules([]);
                        setDueInfo(null);
                      }}
                    >
                      Change
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="relative">
                      <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                      <input
                        type="text"
                        className="input-field py-2.5 pl-9 text-sm"
                        placeholder="Search active customers"
                        value={customerQuery}
                        onChange={(e) => setCustomerQuery(e.target.value)}
                        autoComplete="off"
                      />
                    </div>
                    {customerQuery.trim() && (
                      <div className="mt-2 max-h-40 overflow-y-auto rounded-xl border border-surface-100 bg-white">
                        {customerLoading ? (
                          <p className="px-3 py-3 text-xs text-surface-400">Searching…</p>
                        ) : customerResults.length ? (
                          customerResults.map((customer) => (
                            <button
                              key={customer.id}
                              type="button"
                              onClick={() => selectCustomer(customer)}
                              className="flex w-full items-center justify-between gap-3 border-b border-surface-50 px-3 py-2.5 text-left last:border-b-0 hover:bg-surface-50"
                            >
                              <span className="text-sm font-medium text-surface-900">{customer.full_name}</span>
                              <span className="text-xs text-surface-400">{customer.mobile_number}</span>
                            </button>
                          ))
                        ) : (
                          <p className="px-3 py-3 text-xs text-surface-400">No active customers found.</p>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>

              <div>
                <label className="input-label" htmlFor="finance-collection-account">Finance account</label>
                <select
                  id="finance-collection-account"
                  className="input-field py-2.5 text-sm"
                  value={draft.finance_account_id}
                  onChange={(e) => selectAccount(e.target.value)}
                  disabled={!draft.customer_id || accountsLoading}
                >
                  <option value="">Select a Finance account</option>
                  {eligibleAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.account_number} · {formatCurrency(account.installment_amount)} / {account.frequency.toLowerCase()}
                    </option>
                  ))}
                </select>
                {accountsLoading && <p className="input-hint">Loading eligible Finance accounts…</p>}
              </div>

              {dueInfo && (
                <div className="grid grid-cols-2 gap-2 rounded-xl bg-surface-50 p-3 sm:grid-cols-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-surface-400">Amount due</p>
                    <p className="text-sm font-bold text-surface-900">{formatCurrency(dueInfo.amount_due)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-surface-400">Outstanding</p>
                    <p className="text-sm font-bold text-surface-900">{formatCurrency(dueInfo.outstanding)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-surface-400">Next due</p>
                    <p className="text-sm font-bold text-surface-900">
                      {dueInfo.next_due_date ? formatDate(dueInfo.next_due_date) : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-surface-400">Installment</p>
                    <p className="text-sm font-bold text-surface-900">
                      {dueInfo.next_installment_number ? `#${dueInfo.next_installment_number}` : "—"}
                    </p>
                  </div>
                </div>
              )}

              <div>
                <label className="input-label" htmlFor="finance-collection-schedule">Unpaid installment</label>
                <select
                  id="finance-collection-schedule"
                  className="input-field py-2.5 text-sm"
                  value={draft.finance_schedule_id}
                  onChange={(e) => selectSchedule(e.target.value)}
                  disabled={!draft.finance_account_id || accountsLoading}
                >
                  <option value="">Select an installment</option>
                  {schedules.map((schedule) => (
                    <option
                      key={schedule.id}
                      value={schedule.id}
                      disabled={schedule.remaining_amount <= 0}
                    >
                      #{schedule.installment_number} · due {formatDate(schedule.due_date)} · {formatCurrency(schedule.remaining_amount)}
                      {schedule.remaining_amount <= 0 ? " (paid)" : ""}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="input-label" htmlFor="finance-collection-amount">Amount *</label>
                  <input
                    id="finance-collection-amount"
                    type="number"
                    min="0"
                    step="0.01"
                    className="input-field py-2.5 text-sm"
                    value={draft.amount}
                    onChange={(e) => setDraft((prev) => (prev ? { ...prev, amount: e.target.value } : prev))}
                    required
                  />
                </div>
                <div>
                  <label className="input-label" htmlFor="finance-collection-method">Payment method</label>
                  <select
                    id="finance-collection-method"
                    className="input-field py-2.5 text-sm"
                    value={draft.payment_method}
                    onChange={(e) => setDraft((prev) => (prev ? { ...prev, payment_method: e.target.value } : prev))}
                  >
                    {PAYMENT_METHODS.map((method) => (
                      <option key={method} value={method}>{methodLabel(method)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="input-label" htmlFor="finance-collection-date">Payment date *</label>
                  <input
                    id="finance-collection-date"
                    type="date"
                    className="input-field py-2.5 text-sm"
                    value={draft.payment_date}
                    onChange={(e) => setDraft((prev) => (prev ? { ...prev, payment_date: e.target.value } : prev))}
                    required
                  />
                </div>
                <div>
                  <label className="input-label" htmlFor="finance-collection-reference">Reference number</label>
                  <input
                    id="finance-collection-reference"
                    type="text"
                    className="input-field py-2.5 text-sm"
                    placeholder="Optional"
                    value={draft.reference_number}
                    onChange={(e) => setDraft((prev) => (prev ? { ...prev, reference_number: e.target.value } : prev))}
                  />
                </div>
              </div>

              <div>
                <label className="input-label" htmlFor="finance-collection-notes">Notes</label>
                <textarea
                  id="finance-collection-notes"
                  rows={2}
                  className="input-field py-2.5 text-sm"
                  placeholder="Optional"
                  value={draft.notes}
                  onChange={(e) => setDraft((prev) => (prev ? { ...prev, notes: e.target.value } : prev))}
                />
              </div>

              {modalError && (
                <div className="flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 px-3 py-2.5 text-sm text-danger-700">
                  <AlertTriangle size={15} className="mt-0.5 flex-shrink-0" />
                  <span>{modalError}</span>
                </div>
              )}

              <div className="flex flex-wrap justify-end gap-2 border-t border-surface-100 pt-4">
                <button type="button" onClick={closeModal} className="btn-secondary" disabled={submitting}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={submitting || !draft.customer_id || !draft.finance_account_id || !draft.finance_schedule_id}>
                  {submitting ? "Recording…" : "Record repayment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
