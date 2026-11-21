"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import NumericInput from "@/components/ui/NumericInput";
import Avatar from "@/components/ui/Avatar";
import EmptyState from "@/components/ui/EmptyState";
import { financeApi } from "@/services/finance";
import { paymentsApi } from "@/services/payments";
import { useAuthStore } from "@/hooks/useAuth";
import { getApiErrorMessage, getApiErrorStatus } from "@/services/api-client";
import { cn, formatCurrency, formatDate, getStatusColor } from "@/lib/utils";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Edit3,
  RefreshCw,
  UserRound,
  Wallet,
  X,
} from "lucide-react";
import type { DueInfo, FinanceAccount, FinanceSchedule, Payment } from "@/types";

const STATUSES = ["ACTIVE", "COMPLETED", "DEFAULTED", "CLOSED"];
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
    return `finance-repayment-${crypto.randomUUID()}`;
  }
  return `finance-repayment-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function FinanceDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const permissions = useAuthStore((state) => state.user?.permissions ?? []);

  const [account, setAccount] = useState<FinanceAccount | null>(null);
  const [schedule, setSchedule] = useState<FinanceSchedule[]>([]);
  const [due, setDue] = useState<DueInfo | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [success, setSuccess] = useState("");

  const [showEdit, setShowEdit] = useState(false);
  const [editStatus, setEditStatus] = useState("ACTIVE");
  const [editNotes, setEditNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");

  const [showCollect, setShowCollect] = useState(false);
  const [collectScheduleId, setCollectScheduleId] = useState("");
  const [collectAmount, setCollectAmount] = useState("");
  const [collectMethod, setCollectMethod] = useState("CASH");
  const [collectDate, setCollectDate] = useState(localDate());
  const [collectReference, setCollectReference] = useState("");
  const [collectNotes, setCollectNotes] = useState("");
  const [collecting, setCollecting] = useState(false);
  const [collectError, setCollectError] = useState("");
  const paymentKeyRef = useRef("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setNotFound(false);
    try {
      const [loadedAccount, loadedSchedule] = await Promise.all([
        financeApi.get(id),
        financeApi.getSchedule(id),
      ]);
      setAccount(loadedAccount);
      setSchedule(loadedSchedule);

      // These are supporting views for the account. A failure here must not
      // hide the account or be misreported as "account not found".
      try {
        setDue(await paymentsApi.getDue(loadedAccount.customer_id, loadedAccount.id));
      } catch {
        setDue(null);
      }
      try {
        const history = await paymentsApi.list({
          finance_account_id: loadedAccount.id,
          per_page: 10,
        });
        setPayments(history.data ?? []);
      } catch {
        setPayments([]);
      }
    } catch (e) {
      if (getApiErrorStatus(e) === 404) setNotFound(true);
      else setError(getApiErrorMessage(e, "Unable to load this finance account."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (id) void load();
  }, [id, load]);

  const unpaidSchedules = useMemo(
    () => schedule.filter((item) => item.remaining_amount > 0 && item.status !== "PAID"),
    [schedule],
  );
  const schedulePaid = schedule.reduce((sum, item) => sum + item.paid_amount, 0);
  const totalPaid = due ? due.total_paid : schedulePaid;
  const outstanding = due ? due.outstanding : Math.max(0, (account?.total_payable ?? 0) - schedulePaid);
  const nextDueDate = due?.next_due_date || unpaidSchedules[0]?.due_date || null;
  const nextInstallment = due?.next_installment_number || unpaidSchedules[0]?.installment_number || null;
  const canEdit = permissions.includes("finance:write");
  const canCollect = permissions.includes("payments:create");

  const openEdit = () => {
    if (!account) return;
    setEditStatus(account.status);
    setEditNotes(account.notes ?? "");
    setEditError("");
    setSuccess("");
    setShowEdit(true);
  };

  const saveEdit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!account || saving) return;
    if (!STATUSES.includes(editStatus)) {
      setEditError("Select a valid account status.");
      return;
    }
    setSaving(true);
    setEditError("");
    try {
      const updated = await financeApi.update(account.id, {
        status: editStatus,
        notes: editNotes.trim() || null,
      });
      setAccount(updated);
      setShowEdit(false);
      setSuccess("Finance account details updated.");
    } catch (e) {
      setEditError(getApiErrorMessage(e, "Could not update this finance account."));
    } finally {
      setSaving(false);
    }
  };

  const openCollect = () => {
    if (!account) return;
    const first = unpaidSchedules[0];
    setCollectScheduleId(first?.id ?? "");
    setCollectAmount(first ? String(first.remaining_amount) : "");
    setCollectMethod("CASH");
    setCollectDate(localDate());
    setCollectReference("");
    setCollectNotes("");
    setCollectError("");
    setSuccess("");
    paymentKeyRef.current = newIdempotencyKey();
    setShowCollect(true);
  };

  const submitCollect = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!account || collecting) return;
    const selected = schedule.find((item) => item.id === collectScheduleId);
    const amount = Number(collectAmount);
    if (!selected) {
      setCollectError("Select an unpaid installment.");
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setCollectError("Enter a repayment amount greater than zero.");
      return;
    }
    if (amount > selected.remaining_amount) {
      setCollectError(`Amount cannot exceed ${formatCurrency(selected.remaining_amount)} outstanding for this installment.`);
      return;
    }
    if (!collectDate) {
      setCollectError("Enter the payment date.");
      return;
    }

    setCollecting(true);
    setCollectError("");
    try {
      await paymentsApi.create({
        customer_id: account.customer_id,
        finance_account_id: account.id,
        finance_schedule_id: selected.id,
        amount,
        payment_method: collectMethod,
        payment_date: collectDate,
        reference_number: collectReference.trim() || undefined,
        notes: collectNotes.trim() || undefined,
        idempotency_key: paymentKeyRef.current || newIdempotencyKey(),
      });
      setShowCollect(false);
      setSuccess(`Repayment of ${formatCurrency(amount)} recorded.`);
      await load();
    } catch (e) {
      setCollectError(getApiErrorMessage(e, "Could not record this repayment."));
    } finally {
      setCollecting(false);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="card animate-pulse space-y-4 p-6">
          <div className="h-7 w-56 rounded bg-surface-100" />
          <div className="h-4 w-72 rounded bg-surface-100" />
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {[0, 1, 2, 3].map((item) => <div key={item} className="h-20 rounded-xl bg-surface-50" />)}
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <div className="card flex flex-wrap items-center gap-3 border border-danger-200 bg-danger-50 p-4 text-sm text-danger-700">
          <AlertCircle size={16} />
          <span className="flex-1">{error}</span>
          <button type="button" onClick={() => void load()} className="btn-secondary btn-sm">Retry</button>
          <Link href="/finance" className="btn-secondary btn-sm">Back to Finance</Link>
        </div>
      </DashboardLayout>
    );
  }

  if (notFound || !account) {
    return (
      <DashboardLayout>
        <div className="card">
          <EmptyState
            icon="🔍"
            title="Account not found"
            description="This finance account may have been removed or the link is incorrect."
            action={<Link href="/finance" className="btn-secondary">Back to Finance</Link>}
          />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <Link href="/finance" className="inline-flex items-center gap-1 text-xs font-medium text-surface-500 hover:text-brand-600">
              <ArrowLeft size={14} /> Back to Finance
            </Link>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-surface-900">{account.account_number}</h1>
              <span className={cn("badge", getStatusColor(account.status))}>{account.status}</span>
            </div>
            <p className="text-sm text-surface-500">Finance account details and repayment schedule</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {canCollect && account.status === "ACTIVE" && unpaidSchedules.length > 0 && (
              <button type="button" onClick={openCollect} className="btn-primary">
                <Wallet size={16} /> Collect Repayment
              </button>
            )}
            {canEdit && (
              <button type="button" onClick={openEdit} className="btn-secondary">
                <Edit3 size={16} /> Edit
              </button>
            )}
          </div>
        </div>

        {success && (
          <div className="flex items-center gap-2 rounded-xl border border-success-200 bg-success-50 p-3 text-sm text-success-700">
            <CheckCircle2 size={16} /> {success}
          </div>
        )}

        <div className="card">
          <div className="flex flex-wrap items-center gap-3 border-b border-surface-100 pb-4">
            <Avatar name={account.customer_name || ""} size="md" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-surface-900">{account.customer_name || "Customer unavailable"}</p>
              <p className="text-xs text-surface-500">
                {account.customer_code || "—"} · {account.mobile_number || "—"}
              </p>
            </div>
            {permissions.includes("customers:read") && (
              <Link href={`/customers/${account.customer_id}`} className="btn-secondary btn-sm">
                <UserRound size={14} /> View customer
              </Link>
            )}
          </div>

          <div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-5">
            <div>
              <p className="text-xs text-surface-500">Principal</p>
              <p className="text-lg font-bold text-surface-900">{formatCurrency(account.principal_amount)}</p>
            </div>
            <div>
              <p className="text-xs text-surface-500">Total payable</p>
              <p className="text-lg font-bold text-surface-900">{formatCurrency(account.total_payable)}</p>
            </div>
            <div>
              <p className="text-xs text-surface-500">Total paid</p>
              <p className="text-lg font-bold text-success-600">{formatCurrency(totalPaid)}</p>
            </div>
            <div>
              <p className="text-xs text-surface-500">Outstanding</p>
              <p className="text-lg font-bold text-danger-600">{formatCurrency(outstanding)}</p>
            </div>
            <div>
              <p className="text-xs text-surface-500">Next due</p>
              <p className="text-sm font-semibold text-surface-900">{nextDueDate ? formatDate(nextDueDate) : "—"}</p>
              <p className="text-xs text-surface-500">
                {nextInstallment ? `Installment #${nextInstallment}` : due ? "No pending installment" : "Schedule unavailable"}
              </p>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-4 border-t border-surface-100 pt-4 text-sm md:grid-cols-4">
            <div><span className="text-surface-500">Interest:</span> {account.interest_rate}% ({account.interest_type})</div>
            <div><span className="text-surface-500">Fees:</span> {formatCurrency(account.fees)}</div>
            <div><span className="text-surface-500">Installment:</span> {formatCurrency(account.installment_amount)}</div>
            <div><span className="text-surface-500">Frequency:</span> {account.frequency}</div>
            <div><span className="text-surface-500">Start:</span> {formatDate(account.start_date)}</div>
            <div><span className="text-surface-500">First due:</span> {formatDate(account.first_due_date)}</div>
            <div><span className="text-surface-500">Installments:</span> {account.number_of_installments}</div>
            <div><span className="text-surface-500">Created:</span> {formatDate(account.created_at)}</div>
          </div>
          {account.notes && (
            <div className="mt-4 rounded-xl bg-surface-50 p-3 text-sm text-surface-600">
              <span className="font-medium text-surface-700">Notes:</span> {account.notes}
            </div>
          )}
        </div>

        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-surface-900">Payment Schedule</h2>
            <span className="text-xs text-surface-500">{unpaidSchedules.length} installment(s) remaining</span>
          </div>
          {schedule.length === 0 ? (
            <EmptyState icon="📅" title="No installments" description="This account does not have a generated schedule." />
          ) : (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th><th>Due date</th><th>Expected</th><th>Paid</th><th>Remaining</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {schedule.map((item) => (
                    <tr key={item.id}>
                      <td className="font-medium">{item.installment_number}</td>
                      <td>{formatDate(item.due_date)}</td>
                      <td>{formatCurrency(item.expected_amount)}</td>
                      <td className="font-medium text-success-600">{formatCurrency(item.paid_amount)}</td>
                      <td className="font-medium text-danger-600">{formatCurrency(item.remaining_amount)}</td>
                      <td><span className={cn("badge", getStatusColor(item.status))}>{item.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold text-surface-900">Repayment History</h2>
            <button type="button" onClick={() => void load()} className="btn-secondary btn-sm">
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
          {payments.length === 0 ? (
            <EmptyState icon="🧾" title="No repayments yet" description="Recorded repayments for this account will appear here." />
          ) : (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>Transaction</th><th>Date</th><th>Installment</th><th>Method</th><th>Amount</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((payment) => (
                    <tr key={payment.id}>
                      <td className="font-mono text-xs text-surface-500">{payment.transaction_id}</td>
                      <td>{formatDate(payment.payment_date)}</td>
                      <td>{payment.installment_number ? `#${payment.installment_number}` : "—"}</td>
                      <td>{payment.payment_method}</td>
                      <td className={cn("font-semibold", payment.is_reversal ? "text-danger-600" : "text-success-600")}>
                        {payment.is_reversal ? "−" : "+"}{formatCurrency(payment.amount)}
                      </td>
                      <td><span className={cn("badge", getStatusColor(payment.status))}>{payment.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {showEdit && (
        <div className="modal-backdrop" onClick={() => !saving && setShowEdit(false)}>
          <div className="modal-content max-w-md p-6" onClick={(event) => event.stopPropagation()}>
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-lg font-bold text-surface-900">Edit Finance Account</h2>
              <button type="button" onClick={() => setShowEdit(false)} className="btn-icon" aria-label="Close edit dialog"><X size={18} /></button>
            </div>
            <form onSubmit={saveEdit} className="space-y-4">
              <div>
                <label className="input-label" htmlFor="finance-edit-status">Status</label>
                <select id="finance-edit-status" className="input-field" value={editStatus} onChange={(event) => setEditStatus(event.target.value)}>
                  {STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
                </select>
              </div>
              <div>
                <label className="input-label" htmlFor="finance-edit-notes">Notes</label>
                <textarea id="finance-edit-notes" className="input-field min-h-24" value={editNotes} onChange={(event) => setEditNotes(event.target.value)} placeholder="Optional notes about this account" />
              </div>
              {editError && <p role="alert" className="rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">{editError}</p>}
              <div className="flex justify-end gap-3 border-t border-surface-100 pt-4">
                <button type="button" onClick={() => setShowEdit(false)} className="btn-secondary" disabled={saving}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Saving..." : "Save Changes"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showCollect && (
        <div className="modal-backdrop" onClick={() => !collecting && setShowCollect(false)}>
          <div className="modal-content max-w-lg p-6" onClick={(event) => event.stopPropagation()}>
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-surface-900">Record Repayment</h2>
                <p className="text-xs text-surface-500">{account.account_number} · {account.customer_name}</p>
              </div>
              <button type="button" onClick={() => setShowCollect(false)} className="btn-icon" aria-label="Close repayment dialog"><X size={18} /></button>
            </div>
            <form onSubmit={submitCollect} className="space-y-4">
              <div>
                <label className="input-label" htmlFor="finance-collect-installment">Installment</label>
                <select
                  id="finance-collect-installment"
                  className="input-field"
                  value={collectScheduleId}
                  onChange={(event) => {
                    const selected = schedule.find((item) => item.id === event.target.value);
                    setCollectScheduleId(event.target.value);
                    setCollectAmount(selected ? String(selected.remaining_amount) : "");
                    setCollectError("");
                  }}
                  required
                >
                  <option value="">Select an unpaid installment</option>
                  {unpaidSchedules.map((item) => (
                    <option key={item.id} value={item.id}>
                      #{item.installment_number} · due {formatDate(item.due_date)} · {formatCurrency(item.remaining_amount)} outstanding
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="input-label">Amount</label>
                  <NumericInput value={collectAmount} onValueChange={setCollectAmount} className="input-field" min={0.01} required />
                </div>
                <div>
                  <label className="input-label" htmlFor="finance-collect-method">Method</label>
                  <select id="finance-collect-method" className="input-field" value={collectMethod} onChange={(event) => setCollectMethod(event.target.value)}>
                    {PAYMENT_METHODS.map((method) => <option key={method} value={method}>{method}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="input-label" htmlFor="finance-collect-date">Payment date</label>
                  <input id="finance-collect-date" type="date" className="input-field" value={collectDate} onChange={(event) => setCollectDate(event.target.value)} required />
                </div>
                <div>
                  <label className="input-label" htmlFor="finance-collect-reference">Reference</label>
                  <input id="finance-collect-reference" className="input-field" value={collectReference} onChange={(event) => setCollectReference(event.target.value)} placeholder="Optional" />
                </div>
              </div>
              <div>
                <label className="input-label" htmlFor="finance-collect-notes">Notes</label>
                <textarea id="finance-collect-notes" className="input-field min-h-20" value={collectNotes} onChange={(event) => setCollectNotes(event.target.value)} placeholder="Optional" />
              </div>
              {collectError && <p role="alert" className="rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">{collectError}</p>}
              <div className="flex justify-end gap-3 border-t border-surface-100 pt-4">
                <button type="button" onClick={() => setShowCollect(false)} className="btn-secondary" disabled={collecting}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={collecting || unpaidSchedules.length === 0}>
                  {collecting ? "Recording..." : "Record Repayment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
