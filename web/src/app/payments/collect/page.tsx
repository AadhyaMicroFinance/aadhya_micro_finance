"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import BrandLockup from "@/components/branding/BrandLockup";
import DashboardLayout from "@/components/layout/DashboardLayout";
import NumericInput from "@/components/ui/NumericInput";
import { customersApi } from "@/services/customers";
import { financeApi } from "@/services/finance";
import { paymentsApi } from "@/services/payments";
import { chittiApi } from "@/services/chitti";
import { formatCurrency, formatDate, cn, getStatusColor } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import type { Customer, FinanceAccount, FinanceSchedule } from "@/types";
import type { PendingPaymentRecord } from "@/services/payments";
import { Search, ArrowLeft, CheckCircle2, Zap, ChevronRight } from "lucide-react";

type Step = "search" | "select-account" | "enter-amount" | "success";

export default function CollectPaymentPage() {
  const [step, setStep] = useState<Step>("search");
  const [searchQuery, setSearchQuery] = useState("");
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [accounts, setAccounts] = useState<FinanceAccount[]>([]);
  const [chittiMemberships, setChittiMemberships] = useState<Awaited<ReturnType<typeof paymentsApi.eligibleAccounts>>["chitti_memberships"]>([]);
  const [selectedAccount, setSelectedAccount] = useState<FinanceAccount | null>(null);
  const [selectedChitti, setSelectedChitti] = useState<(typeof chittiMemberships)[number] | null>(null);
  const [schedule, setSchedule] = useState<FinanceSchedule[]>([]);
  const [selectedFinanceScheduleId, setSelectedFinanceScheduleId] = useState<string | null>(null);
  const [selectedChittiPeriod, setSelectedChittiPeriod] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("CASH");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successData, setSuccessData] = useState<{ transaction_id: string; amount: number; date: string; customer: string; account: string; method: string; reference: string } | null>(null);
  const [pendingPayments, setPendingPayments] = useState<PendingPaymentRecord[]>([]);
  const [pendingSearch, setPendingSearch] = useState("");
  const [pendingLoading, setPendingLoading] = useState(true);
  const [pendingError, setPendingError] = useState("");
  const [quickCollecting, setQuickCollecting] = useState<string | null>(null);

  const loadPendingPayments = useCallback(async () => {
    setPendingLoading(true);
    try {
      const records = await paymentsApi.pending();
      const uniqueRecords = new Map<string, PendingPaymentRecord>();
      records.forEach((record) => uniqueRecords.set(record.id, record));
      setPendingPayments(Array.from(uniqueRecords.values()));
      setPendingError("");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: { message?: string } } } };
      setPendingError(err?.response?.data?.error?.message || "Could not load pending payments.");
    } finally {
      setPendingLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPendingPayments();
  }, [loadPendingPayments]);

  const pendingGroups = useMemo(() => {
    const query = pendingSearch.trim().toLocaleLowerCase();
    const filtered = pendingPayments.filter((record) => !query || [
      record.customer_name,
      record.customer_code,
      record.mobile_number,
      record.account_name,
      record.account_code,
      record.source,
      String(record.period_number),
    ].some((value) => value.toLocaleLowerCase().includes(query)));
    filtered.sort((a, b) => a.due_date.localeCompare(b.due_date)
      || a.account_name.localeCompare(b.account_name)
      || a.customer_name.localeCompare(b.customer_name)
      || a.period_number - b.period_number);

    const dates = new Map<string, Map<string, PendingPaymentRecord[]>>();
    filtered.forEach((record) => {
      const dateGroups = dates.get(record.due_date) || new Map<string, PendingPaymentRecord[]>();
      const accountKey = `${record.source}:${record.account_code || record.account_id}`;
      const accountRecords = dateGroups.get(accountKey) || [];
      accountRecords.push(record);
      dateGroups.set(accountKey, accountRecords);
      dates.set(record.due_date, dateGroups);
    });
    return Array.from(dates.entries()).map(([date, accountsForDate]) => ({
      date,
      accounts: Array.from(accountsForDate.entries()).map(([key, records]) => ({ key, records })),
    }));
  }, [pendingPayments, pendingSearch]);

  const steps = ["search", "select-account", "enter-amount"] as const;
  const stepIndex = steps.indexOf(step as typeof steps[number]);
  const stepLabels = ["Search Customer", "Select Account", "Record Payment"];

  const searchCustomers = async () => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    try { const res = await customersApi.list({ search: searchQuery, per_page: 20 }); setCustomers(res.data); }
    catch { /* ignore */ } finally { setLoading(false); }
  };

  const selectCustomer = async (c: Customer) => {
    setSelectedCustomer(c);
    setStep("select-account");
    setLoading(true);
    try {
      const res = await paymentsApi.eligibleAccounts(c.id);
      setAccounts(res.finance_accounts as FinanceAccount[]);
      setChittiMemberships(res.chitti_memberships);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: { message?: string } } } };
      setError(err?.response?.data?.error?.message || "Could not load eligible accounts.");
    } finally { setLoading(false); }
  };

  const selectAccount = async (a: FinanceAccount, targetScheduleId?: string) => {
    setSelectedChitti(null);
    setPaymentMethod("CASH");
    setReferenceNumber("");
    setSelectedAccount(a);
    setSelectedFinanceScheduleId(null);
    setSchedule([]);
    setError("");
    setStep("enter-amount");
    setLoading(true);
    try {
      const s = await financeApi.getSchedule(a.id);
      setSchedule(s);
      const now = new Date();
      const todayString = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0");
      const nextDue = targetScheduleId
        ? s.find((x) => x.id === targetScheduleId && x.remaining_amount > 0 && x.due_date <= todayString)
        : s.find((x) => ["DUE", "PARTIALLY_PAID", "OVERDUE", "UPCOMING"].includes(x.status) && x.remaining_amount > 0);
      if (targetScheduleId && !nextDue) {
        setStep("select-account");
        setError("That installment is no longer unpaid and due. Refresh the pending list before collecting.");
        return;
      }
      setSelectedFinanceScheduleId(nextDue?.id || null);
      setAmount(nextDue ? String(nextDue.remaining_amount) : String(a.installment_amount));
      if (!nextDue) setError("This Finance account has no unpaid installment to allocate a payment to.");
    } catch { setError("Could not load the Finance installment schedule."); } finally { setLoading(false); }
  };

  const selectChitti = async (membership: (typeof chittiMemberships)[number], targetPeriod?: number) => {
    setSelectedAccount(null);
    // Chitti accepts only CASH/UPI here. Resetting prevents a Finance-only
    // method from being submitted invisibly after switching sources.
    setPaymentMethod("CASH");
    setReferenceNumber("");
    setSelectedChitti(membership);
    setStep("enter-amount");
    setLoading(true);
    try {
      const entries = await chittiApi.getMemberContributions(membership.chitti_id, membership.member_id);
      setSchedule(entries as unknown as FinanceSchedule[]);
      const now = new Date();
      const todayString = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0");
      const next = targetPeriod !== undefined
        ? entries.find((entry) => entry.period_number === targetPeriod && entry.remaining_amount > 0 && Boolean(entry.due_date && entry.due_date <= todayString))
        : entries.find((entry) => entry.remaining_amount > 0);
      if (targetPeriod !== undefined && !next) {
        setStep("select-account");
        setError("That contribution is no longer unpaid and due. Refresh the pending list before collecting.");
        return;
      }
      if (next) {
        setSelectedChitti({
          ...membership,
          current_period: next.period_number,
          due_date: next.due_date || null,
          amount_due: next.remaining_amount,
        });
      }
      setSelectedChittiPeriod(next?.period_number || null);
      setAmount(next ? String(next.remaining_amount) : String(membership.amount_due));
    } catch {
      setError("Could not load this member's contribution schedule.");
    } finally { setLoading(false); }
  };

  const quickCollect = async (record: PendingPaymentRecord) => {
    if (quickCollecting) return;
    setQuickCollecting(record.id);
    setError("");
    try {
      const customer = await customersApi.get(record.customer_id);
      setSelectedCustomer(customer);
      const eligible = await paymentsApi.eligibleAccounts(customer.id);
      const financeAccounts = eligible.finance_accounts as FinanceAccount[];
      setAccounts(financeAccounts);
      setChittiMemberships(eligible.chitti_memberships);
      if (record.source === "FINANCE") {
        const account = financeAccounts.find((item) => item.id === record.account_id);
        if (!account || !record.schedule_id) {
          throw new Error("This Finance account is no longer available for collection.");
        }
        await selectAccount(account, record.schedule_id);
      } else {
        const membership = eligible.chitti_memberships.find(
          (item) => item.member_id === record.member_id && item.chitti_id === record.account_id,
        );
        if (!membership) {
          throw new Error("This Chitti membership is no longer eligible for collection.");
        }
        await selectChitti(membership, record.period_number);
      }
    } catch (e: unknown) {
      const err = e as { message?: string; response?: { data?: { error?: { message?: string } } } };
      setStep("search");
      setError(err?.response?.data?.error?.message || err.message || "Could not open this payment for collection.");
    } finally {
      setQuickCollecting(null);
    }
  };

  const submitPayment = async () => {
    if (!selectedCustomer || (!selectedAccount && !selectedChitti) || !amount) return;
    if (!selectedChitti && !selectedFinanceScheduleId) {
      setError("Select a Finance installment before recording this repayment.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const now = new Date();
      const paymentDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
      const result = selectedChitti
        ? await chittiApi.recordContribution(selectedChitti.chitti_id, {
          member_id: selectedChitti.member_id,
          period_number: selectedChittiPeriod || selectedChitti.current_period,
          amount: parseFloat(amount),
          payment_method: paymentMethod,
          payment_date: paymentDate,
          reference_number: referenceNumber || undefined,
          notes: notes || undefined,
          idempotency_key: paymentKey,
        }).then((data) => ({ transaction_id: String(data.transaction_id || data.contribution_id || "CHITTI"), amount: parseFloat(amount) }))
        : await paymentsApi.create({
        customer_id: selectedCustomer.id,
        finance_account_id: selectedAccount!.id,
        finance_schedule_id: selectedFinanceScheduleId!,
        amount: parseFloat(amount),
        payment_method: paymentMethod,
        payment_date: paymentDate,
        reference_number: referenceNumber || undefined,
        notes: notes || undefined,
        idempotency_key: paymentKey,
      });
      setSuccessData({
        transaction_id: result.transaction_id,
        amount: result.amount,
        date: paymentDate,
        customer: selectedCustomer.full_name,
        account: selectedChitti ? `${selectedChitti.chitti_name} · Member #${selectedChitti.member_number} · Period ${selectedChittiPeriod || selectedChitti.current_period}` : `Finance · ${selectedAccount!.account_number}`,
        method: paymentMethod,
        reference: referenceNumber,
      });
      setStep("success");
      void loadPendingPayments();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: { message?: string } } } };
      setError(err?.response?.data?.error?.message || "Payment failed. Please try again.");
    } finally { setLoading(false); }
  };

  const [referenceNumber, setReferenceNumber] = useState("");
  const [paymentKey, setPaymentKey] = useState(() => `collect-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const selectedFinanceSchedule = schedule.find((item) => item.id === selectedFinanceScheduleId);

  const reset = () => {
    setStep("search"); setSearchQuery(""); setCustomers([]); setSelectedCustomer(null);
    setAccounts([]); setChittiMemberships([]); setSelectedAccount(null); setSelectedChitti(null); setSchedule([]); setSelectedFinanceScheduleId(null); setSelectedChittiPeriod(null); setAmount("");
    setPaymentMethod("CASH"); setNotes(""); setError(""); setSuccessData(null);
    setReferenceNumber(""); setPaymentKey(`collect-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  };

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-6xl space-y-6 print:hidden">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight flex items-center gap-2"><Zap size={24} className="text-brand-600" /> Collect Payment</h1>
        </div>

        {/* Step Indicator */}
        {step !== "success" && (
          <div className="max-w-2xl flex items-center gap-2">
            {stepLabels.map((label, i) => (
              <div key={label} className="flex items-center gap-2 flex-1">
                <div className={cn("flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors", i < stepIndex ? "bg-success-600 text-white" : i === stepIndex ? "bg-brand-600 text-white" : "bg-surface-100 text-surface-400")}>
                  {i < stepIndex ? "✓" : i + 1}
                </div>
                <span className={cn("text-xs font-medium hidden sm:inline", i <= stepIndex ? "text-surface-900" : "text-surface-400")}>{label}</span>
                {i < stepLabels.length - 1 && <ChevronRight size={14} className="text-surface-300 mx-1" />}
              </div>
            ))}
          </div>
        )}

        {/* Step 1: Search */}
        {step === "search" && (
          <>
            <div className="card max-w-2xl space-y-4 animate-fade-in">
              <h3 className="text-sm font-semibold text-surface-900">Search Customer</h3>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-surface-400" />
                  <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchCustomers()} placeholder="Search by name, code, or mobile..." className="input-field pl-10" autoFocus />
                </div>
                <button onClick={searchCustomers} className="btn-primary" disabled={loading}>Search</button>
              </div>
              {error && <div role="alert" className="rounded-xl border border-danger-100 bg-danger-50 p-3 text-sm text-danger-700">{error}</div>}
              {customers.length > 0 && (
                <div className="space-y-2">
                  {customers.map((c) => (
                    <button key={c.id} onClick={() => selectCustomer(c)} className="flex w-full items-center gap-3 rounded-xl border border-surface-100 p-4 text-left transition-all hover:border-surface-200 hover:shadow-sm">
                      <Avatar name={c.full_name} size="md" />
                      <div className="flex-1"><p className="text-sm font-semibold text-surface-900">{c.full_name}</p><p className="text-xs text-surface-500">{c.customer_code} • {c.mobile_number}</p></div>
                      <ChevronRight size={16} className="text-surface-300" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <section className="card space-y-4" aria-labelledby="pending-payments-heading">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 id="pending-payments-heading" className="text-sm font-semibold text-surface-900">Pending Payments</h3>
                  <p className="mt-1 text-xs text-surface-500">Grouped by due date, then Finance account or Chitti. Oldest due dates appear first.</p>
                </div>
                <button onClick={() => void loadPendingPayments()} disabled={pendingLoading} className="btn-secondary text-sm">
                  {pendingLoading ? "Refreshing…" : "Refresh balances"}
                </button>
              </div>

              {!pendingLoading && !pendingError && pendingPayments.length > 0 && (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="relative min-w-[min(100%,18rem)] flex-1">
                    <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-surface-400" />
                    <input
                      type="search"
                      value={pendingSearch}
                      onChange={(event) => setPendingSearch(event.target.value)}
                      placeholder="Filter by customer, mobile, Chitti, or account..."
                      aria-label="Filter pending payments"
                      className="input-field pl-10"
                    />
                  </div>
                  <p className="text-xs text-surface-500" aria-live="polite">
                    {pendingGroups.reduce((total, group) => total + group.accounts.reduce((count, account) => count + account.records.length, 0), 0)} of {pendingPayments.length} due records
                  </p>
                </div>
              )}

              {pendingLoading ? (
                <div className="py-8 text-center text-sm text-surface-500" role="status">Loading pending payments…</div>
              ) : pendingError ? (
                <div className="rounded-xl border border-danger-100 bg-danger-50 p-4 text-sm text-danger-700" role="alert">
                  <p>{pendingError}</p>
                  <button onClick={() => void loadPendingPayments()} className="mt-2 font-semibold underline">Try again</button>
                </div>
              ) : pendingPayments.length === 0 ? (
                <div className="rounded-xl bg-surface-50 px-4 py-8 text-center">
                  <p className="text-sm font-medium text-surface-700">No pending payments due</p>
                  <p className="mt-1 text-xs text-surface-500">Future periods and fully settled records are not shown.</p>
                </div>
              ) : pendingGroups.length === 0 ? (
                <div className="rounded-xl bg-surface-50 px-4 py-8 text-center">
                  <p className="text-sm font-medium text-surface-700">No matching pending payments</p>
                  <p className="mt-1 text-xs text-surface-500">Try a customer name, customer ID, mobile number, or Chitti/account name.</p>
                </div>
              ) : (
                <div className="max-h-[65vh] space-y-5 overflow-y-auto overscroll-contain pr-2" aria-label="Pending payment records">
                  {pendingGroups.map((dateGroup) => (
                    <section key={dateGroup.date} aria-label={`Due ${formatDate(dateGroup.date)}`}>
                      <h4 className="sticky top-0 z-10 -mx-1 mb-3 rounded-lg bg-white/95 px-2 py-2 text-sm font-semibold text-surface-800 shadow-sm backdrop-blur">
                        Due {formatDate(dateGroup.date)}
                        <span className="ml-2 text-xs font-normal text-surface-500">
                          {dateGroup.accounts.reduce((total, account) => total + account.records.length, 0)} payment{dateGroup.accounts.reduce((total, account) => total + account.records.length, 0) === 1 ? "" : "s"}
                        </span>
                      </h4>
                      <div className="space-y-4">
                        {dateGroup.accounts.map((accountGroup) => {
                          const first = accountGroup.records[0];
                          return (
                            <section key={`${dateGroup.date}:${accountGroup.key}`} className="space-y-2" aria-label={`${first.source} ${first.account_name}`}>
                              <h5 className="flex flex-wrap items-center gap-2 text-xs font-semibold text-surface-600">
                                <span className={cn("badge", first.source === "FINANCE" ? "badge-brand" : "bg-purple-50 text-purple-700")}>{first.source}</span>
                                <span>{first.account_name}</span>
                                <span className="font-mono font-normal text-surface-400">{first.account_code}</span>
                                <span className="font-normal text-surface-400">({accountGroup.records.length})</span>
                              </h5>
                              <div className="space-y-2">
                                {accountGroup.records.map((record) => (
                                  <article key={record.id} className="grid gap-4 rounded-xl border border-surface-100 p-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
                                    <div className="min-w-0 space-y-3">
                                      <div className="flex flex-wrap items-start justify-between gap-2">
                                        <div className="min-w-0">
                                          <p className="truncate text-sm font-semibold text-surface-900">{record.customer_name}</p>
                                          <p className="text-xs text-surface-500">Customer ID: {record.customer_code} · {record.mobile_number}</p>
                                        </div>
                                        <span className={cn("badge", getStatusColor(record.status))}>{record.status.replace(/_/g, " ")}</span>
                                      </div>
                                      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
                                        {record.source === "CHITTI" && (
                                          <div><dt className="text-surface-500">Slot</dt><dd className="mt-0.5 font-medium text-surface-800">#{record.member_number}{record.member_alias ? ` · ${record.member_alias}` : ""}</dd></div>
                                        )}
                                        <div><dt className="text-surface-500">{record.source === "FINANCE" ? "Installment" : "Contribution period"}</dt><dd className="mt-0.5 font-medium text-surface-800">{record.period_number}</dd></div>
                                        <div><dt className="text-surface-500">Due date</dt><dd className="mt-0.5 font-medium text-surface-800">{formatDate(record.due_date)}</dd></div>
                                        <div><dt className="text-surface-500">Expected</dt><dd className="mt-0.5 font-medium text-surface-800">{formatCurrency(record.expected_amount)}</dd></div>
                                        <div><dt className="text-surface-500">Outstanding</dt><dd className="mt-0.5 font-semibold text-warning-700">{formatCurrency(record.outstanding_amount)}</dd></div>
                                      </dl>
                                    </div>
                                    <button onClick={() => void quickCollect(record)} disabled={quickCollecting !== null} className="btn-primary w-full lg:w-auto">
                                      {quickCollecting === record.id ? "Opening…" : "Collect"}
                                    </button>
                                  </article>
                                ))}
                              </div>
                            </section>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              )}
            </section>
          </>
        )}

        {/* Step 2: Select Account */}
        {step === "select-account" && (
          <div className="card max-w-2xl space-y-4 animate-fade-in">
            <h3 className="text-sm font-semibold text-surface-900">Select Account for <span className="text-brand-600">{selectedCustomer?.full_name}</span></h3>
            {error && <div role="alert" className="rounded-xl border border-danger-100 bg-danger-50 p-3 text-sm text-danger-700">{error}</div>}
            {loading ? <p className="text-sm text-surface-500 py-4 text-center">Loading accounts and memberships...</p> : accounts.length === 0 && chittiMemberships.length === 0 ? (
              <p className="text-sm text-surface-500 py-4 text-center">No eligible Finance accounts or running Chitti contributions for this customer.</p>
            ) : <div className="space-y-5">
              {accounts.length > 0 && <section className="space-y-2"><h4 className="text-xs font-bold uppercase tracking-wide text-surface-500">Finance accounts</h4>
                {accounts.map((a) => (
                  <button key={a.id} onClick={() => selectAccount(a)} className="w-full rounded-xl border border-surface-100 p-4 text-left hover:border-surface-200 hover:shadow-sm transition-all">
                    <div className="flex items-center justify-between">
                      <div><p className="text-sm font-semibold font-mono text-brand-600">{a.account_number}</p><p className="text-xs text-surface-500">Installment: {formatCurrency(a.installment_amount)} • {a.frequency}</p></div>
                      <span className={cn("badge", getStatusColor(a.status))}>{a.status}</span>
                    </div>
                  </button>
                ))}
              </section>}
              {chittiMemberships.length > 0 && <section className="space-y-2"><h4 className="text-xs font-bold uppercase tracking-wide text-surface-500">Chitti memberships</h4>
                {chittiMemberships.map((m) => <button key={m.member_id} onClick={() => selectChitti(m)} className="w-full rounded-xl border border-purple-100 p-4 text-left hover:border-purple-300">
                  <div className="flex items-start justify-between gap-3"><div><p className="font-semibold">{m.chitti_name} <span className="font-mono text-xs text-surface-500">{m.chitti_code}</span></p><p className="text-xs text-surface-500">Member #{m.member_number}{m.member_alias ? ` · ${m.member_alias}` : ""} · {m.frequency} · Period {m.current_period}{m.due_date ? ` · Due ${m.due_date}` : ""}</p><p className="mt-1 text-xs text-surface-500">Chitti value {formatCurrency(m.total_value)} · Outstanding {formatCurrency(m.outstanding)}</p></div><span className="badge bg-purple-50 text-purple-700">Due {formatCurrency(m.amount_due)}</span></div>
                </button>)}
              </section>}
            </div>}
            <button onClick={() => setStep("search")} className="btn-ghost text-sm"><ArrowLeft size={14} /> Back to Search</button>
          </div>
        )}

        {/* Step 3: Enter Amount */}
        {step === "enter-amount" && (selectedAccount || selectedChitti) && (
          <div className="card max-w-2xl space-y-5 animate-fade-in">
            <h3 className="text-sm font-semibold text-surface-900">Record Payment</h3>
            <div className="rounded-xl bg-surface-50 p-4 text-sm">
              {selectedAccount ? <><p>Finance account: <span className="font-mono font-semibold">{selectedAccount.account_number}</span></p><p>Installment {selectedFinanceSchedule?.installment_number ?? "—"} · Due {formatDate(selectedFinanceSchedule?.due_date || "")} · Outstanding <span className="font-semibold">{formatCurrency(selectedFinanceSchedule?.remaining_amount || 0)}</span></p></> : <><p>Chitti: <span className="font-semibold">{selectedChitti?.chitti_name} ({selectedChitti?.chitti_code})</span></p><p>Member #{selectedChitti?.member_number}{selectedChitti?.member_alias ? ` · ${selectedChitti.member_alias}` : ""} · Period {selectedChittiPeriod || selectedChitti?.current_period} · Due {formatDate(selectedChitti?.due_date || "")}</p><p>Outstanding: <span className="font-semibold">{formatCurrency(selectedChitti?.amount_due || 0)}</span> for this period</p></>}
            </div>

            {error && <div className="rounded-xl bg-danger-50 border border-danger-100 p-3 text-sm text-danger-700">{error}</div>}

            <div>
              <label className="input-label">Amount (₹) *</label>
              <NumericInput value={amount} onValueChange={setAmount} className="input-field text-2xl font-bold" placeholder="0" min="1" autoFocus />
            </div>

            <div>
              <label className="input-label">Payment Method *</label>
              <div className="grid grid-cols-2 gap-2">
                {(selectedChitti ? ["CASH", "UPI"] : ["CASH", "UPI", "BANK_TRANSFER", "OTHER"]).map((m) => (
                  <button key={m} onClick={() => setPaymentMethod(m)} className={cn("rounded-xl border-2 p-3 text-sm font-medium transition-all", paymentMethod === m ? "border-brand-500 bg-brand-50 text-brand-700 shadow-sm" : "border-surface-100 text-surface-600 hover:border-surface-200")}>
                    {m === "CASH" ? "💵 Cash" : m === "UPI" ? "📱 UPI" : m === "BANK_TRANSFER" ? "🏦 Bank" : "📝 Other"}
                  </button>
                ))}
              </div>
            </div>

            {paymentMethod === "UPI" && <div><label className="input-label">UPI transaction reference</label><input type="text" value={referenceNumber} onChange={(e) => setReferenceNumber(e.target.value)} className="input-field" placeholder="UPI reference / UTR" /></div>}

            <div>
              <label className="input-label">Notes</label>
              <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} className="input-field" placeholder="Optional notes..." />
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep("select-account")} className="btn-secondary flex-1"><ArrowLeft size={16} /> Back</button>
              <button onClick={submitPayment} disabled={loading || !amount || parseFloat(amount) <= 0 || Boolean(selectedAccount && !selectedFinanceScheduleId)} className="btn-primary flex-1">
                {loading ? "Processing..." : `Save — ${amount ? formatCurrency(parseFloat(amount)) : "₹0"}`}
              </button>
            </div>
          </div>
        )}

        {/* Success */}
        {step === "success" && successData && (
          <div className="card space-y-6 text-center py-12 animate-scale-in">
            <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-success-100 mx-auto">
              <CheckCircle2 size={32} className="text-success-600" />
            </div>
            <div>
              <h3 className="text-xl font-bold text-surface-900">Payment Successful!</h3>
              <p className="mt-1 text-surface-500">{formatCurrency(successData.amount)} recorded</p>
              <p className="mt-1 font-mono text-xs text-surface-400">{successData.transaction_id}</p>
            </div>
            <div className="flex gap-3 max-w-xs mx-auto">
              <button onClick={reset} className="btn-primary flex-1">New Payment</button>
              <button onClick={() => window.location.href = "/payments"} className="btn-secondary flex-1">View All</button>
            </div>
            <button onClick={() => window.print()} className="btn-secondary mx-auto print:hidden">Print / Save Receipt</button>
          </div>
        )}
      </div>
      {step === "success" && successData && <section className="payment-receipt-print mx-auto hidden max-w-2xl border border-surface-200 bg-white p-8 print:block">
        <div className="border-b pb-5"><BrandLockup variant="document" /><p className="mt-2 text-xs">H.No: 10-2-41/1, Sainagar, Sircilla · CIN: U64990TS2025PTC199452</p><p className="text-xs">9182838496 · 9886232471</p></div>
        <h2 className="my-6 text-center text-lg font-semibold">Payment Receipt</h2>
        <dl className="grid grid-cols-2 gap-4 text-sm"><dt>Transaction ID</dt><dd>{successData.transaction_id}</dd><dt>Customer</dt><dd>{successData.customer}</dd><dt>Account / Membership</dt><dd>{successData.account}</dd><dt>Payment date</dt><dd>{successData.date}</dd><dt>Payment method</dt><dd>{successData.method}</dd>{successData.reference && <><dt>Reference</dt><dd>{successData.reference}</dd></>}<dt className="font-bold">Amount received</dt><dd className="font-bold">{formatCurrency(successData.amount)}</dd></dl>
        <p className="mt-10 border-t pt-4 text-xs text-surface-500">Powered by Vayu Integration Services</p>
      </section>}
    </DashboardLayout>
  );
}
