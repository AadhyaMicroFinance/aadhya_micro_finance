"use client";

import { useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { customersApi } from "@/services/customers";
import { financeApi } from "@/services/finance";
import { paymentsApi } from "@/services/payments";
import { formatCurrency, cn, getStatusColor } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import type { Customer, FinanceAccount, FinanceSchedule } from "@/types";
import { Search, ArrowLeft, CheckCircle2, Zap, ChevronRight } from "lucide-react";

type Step = "search" | "select-account" | "enter-amount" | "success";

export default function CollectPaymentPage() {
  const [step, setStep] = useState<Step>("search");
  const [searchQuery, setSearchQuery] = useState("");
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [accounts, setAccounts] = useState<FinanceAccount[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<FinanceAccount | null>(null);
  const [schedule, setSchedule] = useState<FinanceSchedule[]>([]);
  const [amount, setAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("CASH");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successData, setSuccessData] = useState<{ transaction_id: string; amount: number } | null>(null);

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
    try { const res = await financeApi.list({ customer_id: c.id, per_page: 50 }); setAccounts(res.data); }
    catch { /* ignore */ } finally { setLoading(false); }
  };

  const selectAccount = async (a: FinanceAccount) => {
    setSelectedAccount(a);
    setStep("enter-amount");
    setLoading(true);
    try {
      const s = await financeApi.getSchedule(a.id);
      setSchedule(s);
      const nextDue = s.find((x) => x.status === "DUE" || x.status === "PARTIALLY_PAID");
      setAmount(nextDue ? String(nextDue.remaining_amount) : String(a.installment_amount));
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  const submitPayment = async () => {
    if (!selectedCustomer || !selectedAccount || !amount) return;
    setLoading(true);
    setError("");
    try {
      const result = await paymentsApi.create({
        customer_id: selectedCustomer.id,
        finance_account_id: selectedAccount.id,
        amount: parseFloat(amount),
        payment_method: paymentMethod,
        payment_date: new Date().toISOString().split("T")[0],
        notes: notes || undefined,
        idempotency_key: `pay-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      });
      setSuccessData({ transaction_id: result.transaction_id, amount: result.amount });
      setStep("success");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: { message?: string } } } };
      setError(err?.response?.data?.error?.message || "Payment failed. Please try again.");
    } finally { setLoading(false); }
  };

  const reset = () => {
    setStep("search"); setSearchQuery(""); setCustomers([]); setSelectedCustomer(null);
    setAccounts([]); setSelectedAccount(null); setSchedule([]); setAmount("");
    setPaymentMethod("CASH"); setNotes(""); setError(""); setSuccessData(null);
  };

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight flex items-center gap-2"><Zap size={24} className="text-brand-600" /> Collect Payment</h1>
        </div>

        {/* Step Indicator */}
        {step !== "success" && (
          <div className="flex items-center gap-2">
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
          <div className="card space-y-4 animate-fade-in">
            <h3 className="text-sm font-semibold text-surface-900">Search Customer</h3>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-surface-400" />
                <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchCustomers()} placeholder="Search by name, code, or mobile..." className="input-field pl-10" autoFocus />
              </div>
              <button onClick={searchCustomers} className="btn-primary" disabled={loading}>Search</button>
            </div>
            {customers.length > 0 && (
              <div className="space-y-2">
                {customers.map((c) => (
                  <button key={c.id} onClick={() => selectCustomer(c)} className="w-full rounded-xl border border-surface-100 p-4 text-left hover:border-surface-200 hover:shadow-sm transition-all flex items-center gap-3">
                    <Avatar name={c.full_name} size="md" />
                    <div className="flex-1"><p className="text-sm font-semibold text-surface-900">{c.full_name}</p><p className="text-xs text-surface-500">{c.customer_code} • {c.mobile_number}</p></div>
                    <ChevronRight size={16} className="text-surface-300" />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 2: Select Account */}
        {step === "select-account" && (
          <div className="card space-y-4 animate-fade-in">
            <h3 className="text-sm font-semibold text-surface-900">Select Account for <span className="text-brand-600">{selectedCustomer?.full_name}</span></h3>
            {loading ? <p className="text-sm text-surface-500 py-4 text-center">Loading accounts...</p> : accounts.length === 0 ? (
              <p className="text-sm text-surface-500 py-4 text-center">No active finance accounts for this customer.</p>
            ) : (
              <div className="space-y-2">
                {accounts.map((a) => (
                  <button key={a.id} onClick={() => selectAccount(a)} className="w-full rounded-xl border border-surface-100 p-4 text-left hover:border-surface-200 hover:shadow-sm transition-all">
                    <div className="flex items-center justify-between">
                      <div><p className="text-sm font-semibold font-mono text-brand-600">{a.account_number}</p><p className="text-xs text-surface-500">Installment: {formatCurrency(a.installment_amount)} • {a.frequency}</p></div>
                      <span className={cn("badge", getStatusColor(a.status))}>{a.status}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => setStep("search")} className="btn-ghost text-sm"><ArrowLeft size={14} /> Back to Search</button>
          </div>
        )}

        {/* Step 3: Enter Amount */}
        {step === "enter-amount" && selectedAccount && (
          <div className="card space-y-5 animate-fade-in">
            <h3 className="text-sm font-semibold text-surface-900">Record Payment</h3>
            <div className="rounded-xl bg-surface-50 p-4 text-sm">
              <p>Account: <span className="font-mono font-semibold">{selectedAccount.account_number}</span></p>
              <p>Installment: <span className="font-semibold">{formatCurrency(selectedAccount.installment_amount)}</span></p>
            </div>

            {error && <div className="rounded-xl bg-danger-50 border border-danger-100 p-3 text-sm text-danger-700">{error}</div>}

            <div>
              <label className="input-label">Amount (₹) *</label>
              <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="input-field text-2xl font-bold" placeholder="0" min="1" autoFocus />
            </div>

            <div>
              <label className="input-label">Payment Method *</label>
              <div className="grid grid-cols-4 gap-2">
                {["CASH", "UPI", "BANK_TRANSFER", "OTHER"].map((m) => (
                  <button key={m} onClick={() => setPaymentMethod(m)} className={cn("rounded-xl border-2 p-3 text-sm font-medium transition-all", paymentMethod === m ? "border-brand-500 bg-brand-50 text-brand-700 shadow-sm" : "border-surface-100 text-surface-600 hover:border-surface-200")}>
                    {m === "CASH" ? "💵 Cash" : m === "UPI" ? "📱 UPI" : m === "BANK_TRANSFER" ? "🏦 Bank" : "📝 Other"}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="input-label">Notes</label>
              <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} className="input-field" placeholder="Optional notes..." />
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep("select-account")} className="btn-secondary flex-1"><ArrowLeft size={16} /> Back</button>
              <button onClick={submitPayment} disabled={loading || !amount || parseFloat(amount) <= 0} className="btn-primary flex-1">
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
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
