"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { customersApi } from "@/services/customers";
import { formatCurrency, formatDate, getStatusColor } from "@/lib/utils";
import type { Customer, CustomerLedger } from "@/types";

export default function CustomerDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [ledger, setLedger] = useState<CustomerLedger | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [c, l] = await Promise.all([customersApi.get(id), customersApi.getLedger(id)]);
        setCustomer(c);
        setLedger(l);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    if (id) load();
  }, [id]);

  if (loading) return <DashboardLayout><p className="p-6 text-gray-500">Loading...</p></DashboardLayout>;
  if (!customer) return <DashboardLayout><p className="p-6 text-red-500">Customer not found</p></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <Link href="/customers" className="text-gray-400 hover:text-gray-600">← Back</Link>
              <h2 className="text-2xl font-bold text-gray-900">{customer.full_name}</h2>
              <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${getStatusColor(customer.status)}`}>
                {customer.status}
              </span>
            </div>
            <p className="font-mono text-sm text-gray-500 mt-1">{customer.customer_code}</p>
          </div>
        </div>

        {/* Personal Info */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-3 font-semibold text-gray-800 border-b pb-2">Personal Information</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">Full Name</span><span className="font-medium">{customer.full_name}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Date of Birth</span><span className="font-medium">{customer.date_of_birth ? formatDate(customer.date_of_birth) : "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Gender</span><span className="font-medium">{customer.gender || "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Occupation</span><span className="font-medium">{customer.occupation || "—"}</span></div>
            </div>
          </div>

          <div className="card">
            <h3 className="mb-3 font-semibold text-gray-800 border-b pb-2">Contact Details</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">Mobile</span><span className="font-medium">{customer.mobile_number}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Alt Mobile</span><span className="font-medium">{customer.alternate_mobile || "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Email</span><span className="font-medium">{customer.email || "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Address</span><span className="font-medium">{customer.address || "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">City</span><span className="font-medium">{customer.city || "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">State</span><span className="font-medium">{customer.state || "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Pincode</span><span className="font-medium">{customer.pincode || "—"}</span></div>
            </div>
          </div>

          <div className="card">
            <h3 className="mb-3 font-semibold text-gray-800 border-b pb-2">KYC Documents</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">PAN Number</span>
                <span className="font-mono font-medium">{customer.pan_number || "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Aadhar Number</span>
                <span className="font-mono font-medium">{customer.aadhar_number ? `****${customer.aadhar_number.slice(-4)}` : "—"}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 className="mb-3 font-semibold text-gray-800 border-b pb-2">Nominee Details</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-500">Name</span><span className="font-medium">{customer.nominee_name || "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Phone</span><span className="font-medium">{customer.nominee_phone || "—"}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Relation</span><span className="font-medium">{customer.nominee_relation || "—"}</span></div>
            </div>
          </div>
        </div>

        {/* Chitti Memberships */}
        <div className="card">
          <h3 className="mb-4 text-lg font-semibold text-gray-800">Chitti Memberships ({ledger?.chittis?.length || 0})</h3>
          {ledger?.chittis && ledger.chittis.length > 0 ? (
            <div className="space-y-3">
              {ledger.chittis.map((c) => (
                <Link key={c.id} href={`/chitti/${c.id}`}>
                  <div className="flex items-center justify-between rounded-lg border border-gray-200 p-4 hover:bg-gray-50">
                    <div>
                      <p className="font-medium text-primary-600">{c.name}</p>
                      <p className="text-sm text-gray-500">{c.chitti_code}</p>
                    </div>
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${getStatusColor(c.status)}`}>
                      {c.status}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">Not a member of any chitti yet.</p>
          )}
        </div>

        {/* Finance Accounts */}
        <div className="card">
          <h3 className="mb-4 text-lg font-semibold text-gray-800">Finance Accounts ({ledger?.finance_accounts?.length || 0})</h3>
          {ledger?.finance_accounts && ledger.finance_accounts.length > 0 ? (
            <div className="space-y-3">
              {ledger.finance_accounts.map((fa) => (
                <div key={fa.id} className="flex items-center justify-between rounded-lg border border-gray-200 p-4">
                  <div>
                    <p className="font-medium text-primary-600">{fa.account_number}</p>
                    <p className="text-sm text-gray-500">Total Payable: {formatCurrency(fa.total_payable)}</p>
                  </div>
                  <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${getStatusColor(fa.status)}`}>
                    {fa.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">No finance accounts yet.</p>
          )}
        </div>

        {/* Payment History */}
        <div className="card">
          <h3 className="mb-4 text-lg font-semibold text-gray-800">Payment History</h3>
          {ledger?.payment_history && ledger.payment_history.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-gray-200 text-xs font-medium uppercase text-gray-500">
                  <tr>
                    <th className="px-3 py-2">Transaction ID</th>
                    <th className="px-3 py-2">Amount</th>
                    <th className="px-3 py-2">Method</th>
                    <th className="px-3 py-2">Date</th>
                    <th className="px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {ledger.payment_history.map((p) => (
                    <tr key={p.id}>
                      <td className="px-3 py-2 font-mono text-xs">{p.transaction_id}</td>
                      <td className="px-3 py-2 font-medium">{formatCurrency(p.amount)}</td>
                      <td className="px-3 py-2">{p.payment_method}</td>
                      <td className="px-3 py-2">{formatDate(p.payment_date)}</td>
                      <td className="px-3 py-2">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${getStatusColor(p.status)}`}>
                          {p.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-gray-500">No payments recorded yet.</p>
          )}
        </div>

        {customer.notes && (
          <div className="card">
            <h3 className="mb-2 font-semibold text-gray-800">Notes</h3>
            <p className="text-sm text-gray-600">{customer.notes}</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
