"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import NumericInput from "@/components/ui/NumericInput";
import Pagination from "@/components/ui/Pagination";
import { financeApi } from "@/services/finance";
import { customersApi } from "@/services/customers";
import { useAuthStore } from "@/hooks/useAuth";
import { getApiErrorMessage } from "@/services/api-client";
import { formatCurrency, formatDate, cn, getStatusColor } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import type { FinanceAccountListItem, Customer } from "@/types";
import { AlertCircle, Plus, X, ChevronRight, Search, Check } from "lucide-react";

const PER_PAGE = 25;

// The exact wording is enforced independently by the backend as well.
const AGREEMENT_CONFIRMATION_TEXT = "I confirm that the agreement has been signed by the customer.";

type ModalAgreement = {
  agreement_id: string;
  agreement_number: string;
  status: string;
  agreement_html?: string;
  agreement_text?: string;
  customer_name?: string;
  customer_code?: string;
  mobile_number?: string;
  terms?: Record<string, unknown>;
  schedule?: Array<{ installment_number: number; due_date: string; expected_amount: number }>;
  generated_at?: string;
  print_count?: number;
  printed_at?: string;
  /** Fingerprint of the form values used to generate this agreement. */
  fingerprint: string;
  /** Local signing confirmation; the backend is the authority. */
  signingConfirmed: boolean;
};

const emptyForm = {
  customer_id: "", principal_amount: "", interest_rate: "0", interest_type: "FLAT",
  fees: "0", frequency: "MONTHLY", start_date: "", first_due_date: "", number_of_installments: "",
};

export default function FinancePage() {
  const [accounts, setAccounts] = useState<FinanceAccountListItem[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  // List-only filters. The account-creation modal keeps its own customer search.
  const [accountSearch, setAccountSearch] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [agreementFilter, setAgreementFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [customerSearch, setCustomerSearch] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [customerLoading, setCustomerLoading] = useState(false);
  const [customerError, setCustomerError] = useState("");
  const [createError, setCreateError] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [creating, setCreating] = useState(false);
  const [agreement, setAgreement] = useState<ModalAgreement | null>(null);
  const [agreementGenerating, setAgreementGenerating] = useState(false);
  const [agreementConfirming, setAgreementConfirming] = useState(false);
  const [agreementBusy, setAgreementBusy] = useState(false);
  const [showAgreementReview, setShowAgreementReview] = useState(false);
  const [agreementError, setAgreementError] = useState("");
  // Once a generated agreement's inputs are edited, it stays invalid even if
  // the operator edits the values back. Only regeneration can make it valid.
  const [agreementInvalidated, setAgreementInvalidated] = useState(false);
  const customerRequestRef = useRef(0);
  const canCreate = useAuthStore((state) => state.user?.permissions ?? []).includes("finance:create");

  const loadAccounts = useCallback(async (nextPage: number) => {
    setLoading(true);
    setError("");
    try {
      const res = await financeApi.list({
        page: nextPage,
        per_page: PER_PAGE,
        search: searchTerm || undefined,
        status: statusFilter || undefined,
        agreement_status: agreementFilter || undefined,
      });
      setAccounts(res.data ?? []);
      setTotal(res.meta?.total ?? 0);
      setTotalPages(Math.max(1, res.meta?.total_pages ?? 1));
    } catch (e) {
      setError(getApiErrorMessage(e, "Unable to load finance accounts."));
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [searchTerm, statusFilter, agreementFilter]);

  // Debounce the list search without touching the modal's customer picker.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchTerm(accountSearch.trim());
      setPage(1);
    }, accountSearch.trim() ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [accountSearch]);

  const loadCustomers = useCallback(async (query: string) => {
    const requestId = ++customerRequestRef.current;
    setCustomerLoading(true);
    setCustomerError("");
    try {
      const res = await customersApi.list({
        search: query.trim() || undefined,
        status: "ACTIVE",
        per_page: 50,
      });
      // An older, slower response must never overwrite a newer search result.
      if (requestId !== customerRequestRef.current) return;
      const unique = new Map<string, Customer>();
      (res.data ?? []).forEach((customer) => unique.set(customer.id, customer));
      setCustomers(Array.from(unique.values()));
    } catch (e) {
      if (requestId !== customerRequestRef.current) return;
      setCustomerError(getApiErrorMessage(e, "Unable to load customers."));
      setCustomers([]);
    } finally {
      if (requestId === customerRequestRef.current) setCustomerLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAccounts(page);
  }, [page, loadAccounts]);

  useEffect(() => {
    if (!showCreate) return;
    const timer = window.setTimeout(
      () => void loadCustomers(customerSearch),
      customerSearch.trim() ? 250 : 0,
    );
    return () => window.clearTimeout(timer);
  }, [showCreate, customerSearch, loadCustomers]);

  const resetCreateForm = useCallback(() => {
    customerRequestRef.current += 1;
    setCustomerSearch("");
    setCustomers([]);
    setSelectedCustomer(null);
    setCustomerLoading(false);
    setCustomerError("");
    setCreateError("");
    setForm(emptyForm);
    setAgreement(null);
    setAgreementError("");
    setAgreementGenerating(false);
    setAgreementConfirming(false);
    setAgreementBusy(false);
    setShowAgreementReview(false);
    setAgreementInvalidated(false);
  }, []);

  const closeCreate = () => {
    if (creating) return;
    resetCreateForm();
    setShowCreate(false);
  };

  const selectCustomer = (customer: Customer) => {
    setSelectedCustomer(customer);
    setForm((current) => ({ ...current, customer_id: customer.id }));
    setCreateError("");
  };

  const getCustomerDisplay = (account: FinanceAccountListItem) =>
    account.customer_name || customers.find((customer) => customer.id === account.customer_id)?.full_name || "—";

  // Any change to the customer or loan details invalidates the agreement.
  // Comparing fingerprints avoids touching every existing field handler and
  // keeps the approved form behaviour untouched.
  const agreementFingerprint = JSON.stringify({
    customer_id: form.customer_id,
    principal_amount: form.principal_amount,
    interest_rate: form.interest_rate,
    interest_type: form.interest_type,
    fees: form.fees,
    frequency: form.frequency,
    start_date: form.start_date,
    first_due_date: form.first_due_date,
    number_of_installments: form.number_of_installments,
  });
  useEffect(() => {
    if (agreement && agreement.fingerprint !== agreementFingerprint) {
      setAgreementInvalidated(true);
    }
  }, [agreement, agreementFingerprint]);

  const agreementMatchesForm = Boolean(
    agreement && agreement.fingerprint === agreementFingerprint && !agreementInvalidated
  );
  const agreementConfirmed = Boolean(
    agreementMatchesForm && agreement?.status === "CONFIRMED" && agreement?.signingConfirmed,
  );

  const agreementPayload = () => ({
    ...form,
    principal_amount: Number(form.principal_amount),
    interest_rate: Number(form.interest_rate || 0),
    fees: Number(form.fees || 0),
    number_of_installments: Number(form.number_of_installments),
  });

  const validateAgreementInput = () => {
    if (!selectedCustomer || !form.customer_id) return "Select an active customer before generating the agreement.";
    if (!Number.isFinite(Number(form.principal_amount)) || Number(form.principal_amount) <= 0) return "Enter a valid principal amount.";
    if (!Number.isInteger(Number(form.number_of_installments)) || Number(form.number_of_installments) <= 0) return "Enter a valid number of installments.";
    if (!form.start_date || !form.first_due_date) return "Enter both dates before generating the agreement.";
    return "";
  };

  const handleGenerateAgreement = async () => {
    const invalid = validateAgreementInput();
    if (invalid) {
      setAgreementError(invalid);
      return;
    }
    setAgreementGenerating(true);
    setAgreementError("");
    setAgreement(null);
    setAgreementConfirming(false);
    setAgreementInvalidated(false);
    try {
      const data = await financeApi.generateAgreement(agreementPayload());
      setAgreement({ ...data, fingerprint: agreementFingerprint, signingConfirmed: false });
    } catch (e) {
      setAgreementError(getApiErrorMessage(e, "Could not generate the agreement."));
    } finally {
      setAgreementGenerating(false);
    }
  };

  const handleAgreementConfirmation = async (checked: boolean) => {
    if (!agreement || !agreementMatchesForm) return;
    if (!checked) {
      setAgreement({ ...agreement, signingConfirmed: false });
      return;
    }
    setAgreementConfirming(true);
    setAgreementError("");
    try {
      await financeApi.confirmAgreement(agreement.agreement_id, AGREEMENT_CONFIRMATION_TEXT);
      setAgreement({ ...agreement, status: "CONFIRMED", signingConfirmed: true });
    } catch (e) {
      setAgreement({ ...agreement, signingConfirmed: false });
      setAgreementError(getApiErrorMessage(e, "Could not record the signing confirmation."));
    } finally {
      setAgreementConfirming(false);
    }
  };

  const handlePrintAgreement = async () => {
    if (!agreement || !agreementMatchesForm) return;
    setAgreementBusy(true);
    setAgreementError("");
    try {
      const updated = await financeApi.printAgreement(agreement.agreement_id);
      const current = { ...agreement, ...updated, fingerprint: agreementFingerprint };
      setAgreement(current);
      const printWindow = window.open("", "_blank");
      if (printWindow) {
        printWindow.document.write(updated.agreement_html || agreement.agreement_html || "<pre></pre>");
        printWindow.document.close();
        printWindow.focus();
        printWindow.print();
      } else {
        setAgreementError("Allow pop-ups to print the agreement, or use Download instead.");
      }
    } catch (e) {
      setAgreementError(getApiErrorMessage(e, "Could not prepare the agreement for printing."));
    } finally {
      setAgreementBusy(false);
    }
  };

  const handleDownloadAgreement = async () => {
    if (!agreement || !agreementMatchesForm) return;
    setAgreementBusy(true);
    setAgreementError("");
    try {
      // Download is a read-only review operation: use the GET endpoint so it
      // does not increment the agreement's print count.
      const agreementDocument = await financeApi.getAgreement(agreement.agreement_id);
      const blob = new Blob([agreementDocument.agreement_html || agreementDocument.agreement_text || ""], {
        type: "text/html;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${agreement.agreement_number || "finance-agreement"}.html`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setAgreementError(getApiErrorMessage(e, "Could not download the agreement."));
    } finally {
      setAgreementBusy(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (creating) return;

    const principal = Number(form.principal_amount);
    const interestRate = Number(form.interest_rate || 0);
    const fees = Number(form.fees || 0);
    const installments = Number(form.number_of_installments);

    if (!selectedCustomer || !form.customer_id) {
      setCreateError("Select an active customer before creating the account.");
      return;
    }
    if (!Number.isFinite(principal) || principal <= 0) {
      setCreateError("Enter a principal amount greater than zero.");
      return;
    }
    if (!Number.isFinite(interestRate) || interestRate < 0 || !Number.isFinite(fees) || fees < 0) {
      setCreateError("Interest rate and fees cannot be negative.");
      return;
    }
    if (!Number.isInteger(installments) || installments <= 0) {
      setCreateError("Enter a whole number of installments greater than zero.");
      return;
    }
    if (!form.start_date || !form.first_due_date) {
      setCreateError("Enter both the start date and first due date.");
      return;
    }
    if (form.first_due_date < form.start_date) {
      setCreateError("First due date cannot be earlier than the start date.");
      return;
    }
    if (!agreementConfirmed || !agreement) {
      setCreateError("Generate the agreement and confirm that it has been signed before creating the account.");
      return;
    }

    setCreating(true);
    setCreateError("");
    try {
      await financeApi.create({
        ...form,
        principal_amount: principal,
        interest_rate: interestRate,
        fees,
        number_of_installments: installments,
        agreement_id: agreement.agreement_id,
      });
      resetCreateForm();
      setShowCreate(false);
      setPage(1);
      await loadAccounts(1);
    } catch (e) {
      setCreateError(getApiErrorMessage(e, "Could not create the finance account."));
    } finally {
      setCreating(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Finance Accounts</h1>
            <p className="mt-1 text-sm text-surface-500">Manage loan accounts and schedules</p>
          </div>
          {canCreate && <button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={16} /> New Account</button>}
        </div>

        {error && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
            <AlertCircle size={16} /> <span className="flex-1">{error}</span>
            <button type="button" onClick={() => void loadAccounts(page)} className="btn-secondary btn-sm">Retry</button>
          </div>
        )}

        <div className="card flex flex-wrap items-end gap-3 p-4">
          <div className="min-w-[220px] flex-1">
            <label className="input-label" htmlFor="finance-account-search">Search accounts</label>
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
              <input
                id="finance-account-search"
                type="search"
                value={accountSearch}
                onChange={(e) => setAccountSearch(e.target.value)}
                placeholder="Customer name, mobile or account ID"
                className="input-field pl-9"
              />
            </div>
          </div>
          <div>
            <label className="input-label" htmlFor="finance-status-filter">Account status</label>
            <select
              id="finance-status-filter"
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
              className="input-field"
            >
              <option value="">All statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="COMPLETED">Completed</option>
              <option value="DEFAULTED">Defaulted</option>
              <option value="CLOSED">Closed</option>
            </select>
          </div>
          <div>
            <label className="input-label" htmlFor="finance-agreement-filter">Agreement</label>
            <select
              id="finance-agreement-filter"
              value={agreementFilter}
              onChange={(e) => { setAgreementFilter(e.target.value); setPage(1); }}
              className="input-field"
            >
              <option value="">All agreement states</option>
              <option value="CONFIRMED">Signed</option>
              <option value="GENERATED">Generated</option>
              <option value="PRINTED">Printed</option>
              <option value="NONE">None</option>
            </select>
          </div>
        </div>

        {loading ? <TableSkeleton rows={5} cols={9} /> : accounts.length === 0 ? (
          <EmptyState
            icon="💰"
            title="No finance accounts"
            description={accountSearch || statusFilter || agreementFilter
              ? "No accounts match the current search or filters."
              : "Create your first finance account to start lending."}
            action={canCreate ? <button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={16} /> New Account</button> : undefined}
          />
        ) : (
          <div className="card space-y-4">
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr><th>Account</th><th>Customer</th><th>Principal</th><th>Total Payable</th><th>Installment</th><th>Frequency</th><th>Status</th><th>Agreement</th><th></th></tr>
                </thead>
                <tbody>
                  {accounts.map((a) => {
                    const customerName = getCustomerDisplay(a);
                    return (
                      <tr key={a.id}>
                        <td><Link href={`/finance/${a.id}`} className="text-sm font-semibold font-mono text-brand-600 hover:text-brand-700">{a.account_number}</Link></td>
                        <td><div className="flex items-center gap-2"><Avatar name={customerName === "—" ? "" : customerName} size="sm" /><div><span className="block text-sm font-medium">{customerName}</span><span className="block text-[11px] text-surface-400">{[a.customer_code, a.mobile_number].filter(Boolean).join(" · ") || a.customer_id.slice(0, 8)}</span></div></div></td>
                        <td className="text-sm">{formatCurrency(a.principal_amount)}</td>
                        <td className="text-sm font-semibold">{formatCurrency(a.total_payable)}</td>
                        <td className="text-sm">{formatCurrency(a.installment_amount)}</td>
                        <td className="text-sm text-surface-500">{a.frequency}</td>
                        <td><span className={cn("badge", getStatusColor(a.status))}>{a.status}</span></td>
                        <td>
                          <span className={cn("badge", a.agreement_status === "CONFIRMED" ? "badge-success" : a.agreement_status === "NONE" ? "badge-danger" : "badge-warning")}>
                            {a.agreement_status === "CONFIRMED" ? "SIGNED" : (a.agreement_status || "NONE").replace(/_/g, " ")}
                          </span>
                        </td>
                        <td><Link href={`/finance/${a.id}`} className="text-brand-600"><ChevronRight size={16} /></Link></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={page} totalPages={totalPages} total={total} perPage={PER_PAGE} onChange={setPage} disabled={loading} />
          </div>
        )}
      </div>

      {showCreate && (
        <div className="modal-backdrop" onClick={closeCreate}>
          <div className="modal-content max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-surface-900">New Finance Account</h2>
              <button type="button" onClick={closeCreate} className="rounded-lg p-2 text-surface-400 hover:bg-surface-100"><X size={18} /></button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="input-label" htmlFor="finance-customer-search">Customer *</label>
                <div className="relative">
                  <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                  <input
                    id="finance-customer-search"
                    type="text"
                    value={customerSearch}
                    onChange={(e) => setCustomerSearch(e.target.value)}
                    className="input-field pl-9 mb-2"
                    placeholder="Search active customers by name or mobile"
                    autoComplete="off"
                  />
                </div>

                {selectedCustomer && (
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-brand-100 bg-brand-50 px-3 py-2 text-xs">
                    <span className="text-brand-800">
                      Selected: <strong>{selectedCustomer.full_name}</strong> · {selectedCustomer.mobile_number}
                    </span>
                    <button
                      type="button"
                      onClick={() => { setSelectedCustomer(null); setForm((current) => ({ ...current, customer_id: "" })); }}
                      className="font-semibold text-brand-700 underline"
                    >
                      Change
                    </button>
                  </div>
                )}

                <div
                  className="max-h-44 overflow-y-auto overscroll-contain rounded-xl border border-surface-100 bg-white"
                  aria-live="polite"
                  aria-label="Matching active customers"
                >
                  {customerLoading ? (
                    <p className="px-3 py-4 text-center text-xs text-surface-500">Searching active customers…</p>
                  ) : customerError ? (
                    <div className="flex items-center justify-between gap-3 px-3 py-3 text-xs text-danger-700">
                      <span className="flex items-center gap-2"><AlertCircle size={14} /> {customerError}</span>
                      <button type="button" onClick={() => void loadCustomers(customerSearch)} className="font-semibold underline">Retry</button>
                    </div>
                  ) : customers.length === 0 ? (
                    <p className="px-3 py-4 text-center text-xs text-surface-500">
                      {customerSearch.trim()
                        ? `No active customers match “${customerSearch.trim()}”. Try a different name or mobile number.`
                        : "No active customers are available."}
                    </p>
                  ) : (
                    customers.map((customer) => {
                      const isSelected = selectedCustomer?.id === customer.id;
                      return (
                        <button
                          key={customer.id}
                          type="button"
                          onClick={() => selectCustomer(customer)}
                          aria-pressed={isSelected}
                          className={cn(
                            "flex w-full items-center justify-between gap-3 border-b border-surface-100 px-3 py-2.5 text-left last:border-b-0 transition-colors",
                            isSelected ? "bg-brand-50" : "hover:bg-surface-50",
                          )}
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium text-surface-900">{customer.full_name}</span>
                            <span className="block truncate text-xs text-surface-500">{customer.customer_code} · {customer.mobile_number}</span>
                          </span>
                          {isSelected && <Check size={16} className="flex-shrink-0 text-brand-600" />}
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="input-label">Principal Amount *</label><NumericInput value={form.principal_amount} onValueChange={(value) => setForm({ ...form, principal_amount: value })} className="input-field" required /></div>
                <div><label className="input-label">Interest Rate %</label><NumericInput value={form.interest_rate} onValueChange={(value) => setForm({ ...form, interest_rate: value })} className="input-field" /></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="input-label">Interest Type</label><select value={form.interest_type} onChange={(e) => setForm({ ...form, interest_type: e.target.value })} className="input-field"><option value="FLAT">Flat</option><option value="REDUCING">Reducing Balance</option></select></div>
                <div><label className="input-label">Fees</label><NumericInput value={form.fees} onValueChange={(value) => setForm({ ...form, fees: value })} className="input-field" /></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="input-label">Frequency *</label><select value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })} className="input-field"><option value="DAILY">Daily</option><option value="WEEKLY">Weekly</option><option value="MONTHLY">Monthly</option></select></div>
                <div><label className="input-label">Installments *</label><NumericInput integer value={form.number_of_installments} onValueChange={(value) => setForm({ ...form, number_of_installments: value })} className="input-field" required /></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="input-label">Start Date *</label><input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="input-field" required /></div>
                <div><label className="input-label">First Due Date *</label><input type="date" value={form.first_due_date} onChange={(e) => setForm({ ...form, first_due_date: e.target.value })} className="input-field" required /></div>
              </div>
              <section className="space-y-3 rounded-xl border border-surface-100 bg-surface-50/60 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-surface-900">Loan Agreement</h3>
                    <p className="text-xs text-surface-500">Generate, review and confirm the signed agreement before creating the account.</p>
                  </div>
                  {agreement && agreementMatchesForm && (
                    <span className={cn("badge", agreement.status === "CONFIRMED" ? "badge-success" : "badge-warning")}>
                      {agreement.status === "CONFIRMED" ? "SIGNED" : agreement.status.replace(/_/g, " ")}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => void handleGenerateAgreement()} disabled={agreementGenerating || creating} className="btn-secondary btn-sm">
                    {agreementGenerating ? "Generating..." : agreementMatchesForm ? "Regenerate Agreement" : "Generate Agreement"}
                  </button>
                  <button type="button" onClick={() => setShowAgreementReview((visible) => !visible)} disabled={!agreementMatchesForm} className="btn-secondary btn-sm">
                    {showAgreementReview ? "Hide Agreement" : "Review Agreement"}
                  </button>
                  <button type="button" onClick={() => void handlePrintAgreement()} disabled={!agreementMatchesForm || agreementBusy} className="btn-secondary btn-sm">Print</button>
                  <button type="button" onClick={() => void handleDownloadAgreement()} disabled={!agreementMatchesForm || agreementBusy} className="btn-secondary btn-sm">Download</button>
                </div>
                {agreement && !agreementMatchesForm && (
                  <p className="text-xs text-warning-700">Customer or loan details changed. Generate a new agreement and confirm signing again.</p>
                )}
                {showAgreementReview && agreementMatchesForm && agreement && (
                  <div
                    className="max-h-56 overflow-y-auto rounded-lg border border-surface-100 bg-white p-4 text-xs text-surface-700"
                    dangerouslySetInnerHTML={{ __html: agreement.agreement_html || `<pre>${agreement.agreement_text || ""}</pre>` }}
                  />
                )}
                {agreementMatchesForm && agreement && (
                  <label className="flex items-start gap-2 text-xs text-surface-700">
                    <input
                      type="checkbox"
                      checked={agreement.signingConfirmed}
                      disabled={agreementConfirming}
                      onChange={(event) => void handleAgreementConfirmation(event.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-surface-300 text-brand-600"
                    />
                    <span>I confirm that the agreement has been signed by the customer.</span>
                  </label>
                )}
                {agreementError && (
                  <p role="alert" className="rounded-lg border border-danger-200 bg-danger-50 p-2 text-xs text-danger-700">{agreementError}</p>
                )}
              </section>
              {createError && (
                <p role="alert" className="rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">{createError}</p>
              )}
              <div className="flex justify-end gap-3 border-t border-surface-100 pt-4">
                <button type="button" onClick={closeCreate} className="btn-secondary">Cancel</button>
                <button
                  type="submit"
                  disabled={creating || customerLoading || !form.customer_id || !agreementConfirmed}
                  title={!agreementConfirmed ? "Generate the agreement and confirm signing first" : undefined}
                  className="btn-primary"
                >
                  {creating ? "Creating..." : "Create Account"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
