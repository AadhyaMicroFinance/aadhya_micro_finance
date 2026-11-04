"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { paymentsApi } from "@/services/payments";
import { formatCurrency, formatDate, cn, getStatusColor } from "@/lib/utils";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import type { Payment } from "@/types";
import { CreditCard, ArrowDownRight, ArrowUpRight, Zap } from "lucide-react";

export default function PaymentsPage() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);

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
                <tr><th>Transaction ID</th><th>Amount</th><th>Method</th><th>Date</th><th>Status</th><th>Reversal</th></tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td className="font-mono text-xs text-surface-500">{p.transaction_id}</td>
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
