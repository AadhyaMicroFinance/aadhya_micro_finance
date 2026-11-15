"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { paymentsApi } from "@/services/payments";
import { formatCurrency, formatDate, cn, getStatusColor } from "@/lib/utils";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import type { Payment } from "@/types";
import { ArrowDownRight, ArrowUpRight, Printer, X, Zap } from "lucide-react";
import BrandLockup from "@/components/branding/BrandLockup";

export default function PaymentsPage() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedReceipt, setSelectedReceipt] = useState<Payment | null>(null);

  useEffect(() => {
    const load = async () => {
      try { const res = await paymentsApi.list({ per_page: 100 }); setPayments(res.data); }
      catch (e) { console.error(e); }
      finally { setLoading(false); }
    };
    load();
  }, []);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Payments</h1>
            <p className="mt-1 text-sm text-surface-500">Payment transaction history</p>
          </div>
          <Link href="/payments/collect" className="btn-primary"><Zap size={16} /> Collect Payment</Link>
        </div>

        {loading ? <TableSkeleton rows={5} cols={6} /> : payments.length === 0 ? (
          <EmptyState icon="💳" title="No payments yet" description="Record your first payment to see it here." action={<Link href="/payments/collect" className="btn-primary"><Zap size={16} /> Collect Payment</Link>} />
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr><th>Transaction ID</th><th>Customer / member</th><th>Account</th><th>Period</th><th>Amount</th><th>Method</th><th>Date</th><th>Status</th><th>Reversal</th><th>Receipt</th></tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td className="font-mono text-xs text-surface-500">{p.transaction_id}</td>
                    <td className="text-sm">{p.member_name || p.customer_name || "—"}</td>
                    <td className="text-sm">{p.account_type === "CHITTI" ? p.chitti_name || "Chitti" : "Finance"}</td>
                    <td className="text-sm">{p.period_number ? `Period ${p.period_number}` : "—"}</td>
                    <td>
                      <div className="flex items-center gap-2">
                        {p.is_reversal ? <ArrowUpRight size={14} className="text-danger-500" /> : <ArrowDownRight size={14} className="text-success-500" />}
                        <span className="text-sm font-semibold">{formatCurrency(p.amount)}</span>
                      </div>
                    </td>
                    <td className="text-sm">{p.payment_method}</td>
                    <td className="text-sm text-surface-500">{formatDate(p.payment_date)}</td>
                    <td><span className={cn("badge", getStatusColor(p.status))}>{p.status}</span></td>
                    <td>{p.is_reversal ? <span className="badge-danger">Reversal</span> : <span className="text-surface-300">—</span>}</td>
                    <td><button className="btn-secondary btn-sm" onClick={() => setSelectedReceipt(p)}>View / Print</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {selectedReceipt && (
        <div className="modal-backdrop print:hidden" onClick={() => setSelectedReceipt(null)}>
          <div className="modal-content max-w-xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-surface-100 px-5 py-4">
              <h2 className="font-semibold">{selectedReceipt.is_reversal ? "Payment reversal" : "Payment receipt"}</h2>
              <button className="btn-icon" onClick={() => setSelectedReceipt(null)} aria-label="Close receipt"><X size={18} /></button>
            </div>
            <section className="payment-receipt-print p-6 sm:p-8">
              <div className="border-b pb-5">
                <BrandLockup variant="document" />
                <p className="mt-2 text-xs">H.No: 10-2-41/1, Sainagar, Sircilla · CIN: U64990TS2025PTC199452</p>
                <p className="text-xs">9182838496 · 9886232471</p>
              </div>
              <h3 className="my-6 text-center text-lg font-semibold">
                {selectedReceipt.is_reversal ? "Payment Reversal" : "Payment Receipt"}
              </h3>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <dt>Transaction ID</dt><dd className="break-all font-mono text-xs">{selectedReceipt.transaction_id}</dd>
                <dt>Customer / member</dt><dd>{selectedReceipt.member_name || selectedReceipt.customer_name || "—"}</dd>
                <dt>Account</dt><dd>{selectedReceipt.account_type === "CHITTI" ? selectedReceipt.chitti_name || "Chitti" : "Finance"}</dd>
                {selectedReceipt.period_number && <><dt>Contribution period</dt><dd>{selectedReceipt.period_number}</dd></>}
                <dt>Payment date</dt><dd>{formatDate(selectedReceipt.payment_date)}</dd>
                <dt>Payment method</dt><dd>{selectedReceipt.payment_method}</dd>
                {selectedReceipt.reference_number && <><dt>Reference</dt><dd>{selectedReceipt.reference_number}</dd></>}
                <dt>Status</dt><dd>{selectedReceipt.status}</dd>
                <dt className="font-bold">Amount</dt><dd className="font-bold">{formatCurrency(selectedReceipt.amount)}</dd>
              </dl>
              <p className="mt-10 border-t pt-4 text-xs text-surface-500">Powered by Vayu Integration Services</p>
            </section>
            <div className="flex justify-end gap-2 border-t border-surface-100 px-5 py-4 print:hidden">
              <button className="btn-secondary" onClick={() => setSelectedReceipt(null)}>Close</button>
              <button className="btn-primary" onClick={() => window.print()}><Printer size={16} /> Print / Save</button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
