"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { financeApi } from "@/services/finance";
import { formatCurrency, formatDate, getStatusColor } from "@/lib/utils";
import type { FinanceAccount, FinanceSchedule } from "@/types";

export default function FinanceDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [account, setAccount] = useState<FinanceAccount | null>(null);
  const [schedule, setSchedule] = useState<FinanceSchedule[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [a, s] = await Promise.all([financeApi.get(id), financeApi.getSchedule(id)]);
        setAccount(a);
        setSchedule(s);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    if (id) load();
  }, [id]);

  if (loading) return <DashboardLayout><p className="p-6 text-gray-500">Loading...</p></DashboardLayout>;
  if (!account) return <DashboardLayout><p className="p-6 text-red-500">Account not found</p></DashboardLayout>;

  const totalPaid = schedule.reduce((sum, s) => sum + s.paid_amount, 0);
  const totalOutstanding = account.total_payable - totalPaid;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Account Info */}
        <div className="card">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-2xl font-bold text-gray-900">{account.account_number}</h2>
              <p className="text-sm text-gray-500">Finance Account</p>
            </div>
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${getStatusColor(account.status)}`}>
              {account.status}
            </span>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <p className="text-xs text-gray-500">Principal Amount</p>
              <p className="text-lg font-bold">{formatCurrency(account.principal_amount)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Total Payable</p>
              <p className="text-lg font-bold">{formatCurrency(account.total_payable)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Total Paid</p>
              <p className="text-lg font-bold text-green-600">{formatCurrency(totalPaid)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Outstanding</p>
              <p className="text-lg font-bold text-red-600">{formatCurrency(totalOutstanding)}</p>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <div><span className="text-gray-500">Interest:</span> {account.interest_rate}% ({account.interest_type})</div>
            <div><span className="text-gray-500">Fees:</span> {formatCurrency(account.fees)}</div>
            <div><span className="text-gray-500">Installment:</span> {formatCurrency(account.installment_amount)}</div>
            <div><span className="text-gray-500">Frequency:</span> {account.frequency}</div>
            <div><span className="text-gray-500">Start:</span> {formatDate(account.start_date)}</div>
            <div><span className="text-gray-500">First Due:</span> {formatDate(account.first_due_date)}</div>
            <div><span className="text-gray-500">Installments:</span> {account.number_of_installments}</div>
          </div>
        </div>

        {/* Payment Schedule */}
        <div className="card">
          <h3 className="mb-4 text-lg font-semibold text-gray-800">Payment Schedule</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-gray-200 text-xs font-medium uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">#</th>
                  <th className="px-4 py-3">Due Date</th>
                  <th className="px-4 py-3">Expected</th>
                  <th className="px-4 py-3">Paid</th>
                  <th className="px-4 py-3">Remaining</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {schedule.map((s) => (
                  <tr key={s.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">{s.installment_number}</td>
                    <td className="px-4 py-3">{formatDate(s.due_date)}</td>
                    <td className="px-4 py-3">{formatCurrency(s.expected_amount)}</td>
                    <td className="px-4 py-3 font-medium text-green-600">{formatCurrency(s.paid_amount)}</td>
                    <td className="px-4 py-3 font-medium text-red-600">{formatCurrency(s.remaining_amount)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${getStatusColor(s.status)}`}>
                        {s.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
