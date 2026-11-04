"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { financeApi } from "@/services/finance";
import { formatCurrency, formatDate, cn, getStatusColor } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import type { FinanceAccount } from "@/types";
import { Plus, X, Wallet, ChevronRight } from "lucide-react";
import { customersApi } from "@/services/customers";
import type { Customer } from "@/types";

export default function FinancePage() {
  const [accounts, setAccounts] = useState<FinanceAccount[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    customer_id: "", principal_amount: "", interest_rate: "0", interest_type: "FLAT",
    fees: "0", frequency: "MONTHLY", start_date: "", first_due_date: "", number_of_installments: "",
  });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [accRes, custRes] = await Promise.all([
          financeApi.list({ per_page: 50 }),
          customersApi.list({ per_page: 100 }),
        ]);
        setAccounts(accRes.data);
        setCustomers(custRes.data);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    };
    load();
  }, []);

  const getCustomerName = (id: string) => customers.find((c) => c.id === id);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      await financeApi.create({
        ...form,
        principal_amount: parseFloat(form.principal_amount),
        interest_rate: parseFloat(form.interest_rate),
        fees: parseFloat(form.fees),
        number_of_installments: parseInt(form.number_of_installments),
      });
      setShowCreate(false);
      const res = await financeApi.list({ per_page: 50 });
      setAccounts(res.data);
    } catch (e) { console.error(e); }
    finally { setCreating(false); }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Finance Accounts</h1>
            <p className="mt-1 text-sm text-surface-500">Manage loan accounts and schedules</p>
          </div>
          <button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={16} /> New Account</button>
        </div>

        {loading ? <TableSkeleton rows={5} cols={7} /> : accounts.length === 0 ? (
          <EmptyState icon="💰" title="No finance accounts" description="Create your first finance account to start lending." action={<button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={16} /> New Account</button>} />
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr><th>Account</th><th>Customer</th><th>Principal</th><th>Total Payable</th><th>Installment</th><th>Frequency</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {accounts.map((a) => {
                  const cust = getCustomerName(a.customer_id);
                  return (
                    <tr key={a.id}>
                      <td><Link href={`/finance/${a.id}`} className="text-sm font-semibold font-mono text-brand-600 hover:text-brand-700">{a.account_number}</Link></td>
                      <td><div className="flex items-center gap-2"><Avatar name={cust?.full_name || ""} size="sm" /><span className="text-sm font-medium">{cust?.full_name || "—"}</span></div></td>
                      <td className="text-sm">{formatCurrency(a.principal_amount)}</td>
                      <td className="text-sm font-semibold">{formatCurrency(a.total_payable)}</td>
                      <td className="text-sm">{formatCurrency(a.installment_amount)}</td>
                      <td className="text-sm text-surface-500">{a.frequency}</td>
                      <td><span className={cn("badge", getStatusColor(a.status))}>{a.status}</span></td>
                      <td><Link href={`/finance/${a.id}`} className="text-brand-600"><ChevronRight size={16} /></Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showCreate && (
        <div className="modal-backdrop" onClick={() => setShowCreate(false)}>
          <div className="modal-content max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-surface-900">New Finance Account</h2>
              <button onClick={() => setShowCreate(false)} className="rounded-lg p-2 text-surface-400 hover:bg-surface-100"><X size={18} /></button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              <div><label className="input-label">Customer ID *</label><input type="text" value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })} className="input-field" placeholder="UUID" required /></div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="input-label">Principal Amount *</label><input type="number" value={form.principal_amount} onChange={(e) => setForm({ ...form, principal_amount: e.target.value })} className="input-field" required /></div>
                <div><label className="input-label">Interest Rate %</label><input type="number" value={form.interest_rate} onChange={(e) => setForm({ ...form, interest_rate: e.target.value })} className="input-field" /></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="input-label">Interest Type</label><select value={form.interest_type} onChange={(e) => setForm({ ...form, interest_type: e.target.value })} className="input-field"><option value="FLAT">Flat</option><option value="REDUCING">Reducing Balance</option></select></div>
                <div><label className="input-label">Fees</label><input type="number" value={form.fees} onChange={(e) => setForm({ ...form, fees: e.target.value })} className="input-field" /></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="input-label">Frequency *</label><select value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })} className="input-field"><option value="DAILY">Daily</option><option value="WEEKLY">Weekly</option><option value="MONTHLY">Monthly</option></select></div>
                <div><label className="input-label">Installments *</label><input type="number" value={form.number_of_installments} onChange={(e) => setForm({ ...form, number_of_installments: e.target.value })} className="input-field" required /></div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="input-label">Start Date *</label><input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="input-field" required /></div>
                <div><label className="input-label">First Due Date *</label><input type="date" value={form.first_due_date} onChange={(e) => setForm({ ...form, first_due_date: e.target.value })} className="input-field" required /></div>
              </div>
              <div className="flex justify-end gap-3 border-t border-surface-100 pt-4">
                <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
                <button type="submit" disabled={creating} className="btn-primary">{creating ? "Creating..." : "Create Account"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
