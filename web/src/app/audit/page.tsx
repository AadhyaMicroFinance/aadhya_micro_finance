"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import EmptyState from "@/components/ui/EmptyState";
import { Search, Shield } from "lucide-react";

export default function AuditPage() {
  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Audit Logs</h1>
          <p className="mt-1 text-sm text-surface-500">Track all system mutations and user actions</p>
        </div>

        <div className="card">
          <div className="flex items-center gap-3 mb-6">
            <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600"><Shield size={18} /></div>
            <h3 className="text-sm font-semibold text-surface-900">Activity Log</h3>
          </div>

          <div className="flex gap-4 mb-6">
            <input type="date" className="input-field" placeholder="From" />
            <input type="date" className="input-field" placeholder="To" />
            <select className="input-field">
              <option value="">All Actions</option>
              <option value="CUSTOMER_CREATED">Customer Created</option>
              <option value="FINANCE_CREATED">Finance Created</option>
              <option value="PAYMENT_CREATED">Payment Created</option>
              <option value="PAYMENT_REVERSED">Payment Reversed</option>
              <option value="USER_CREATED">User Created</option>
              <option value="SETTINGS_CHANGED">Settings Changed</option>
            </select>
          </div>

          <EmptyState icon="📝" title="No audit entries yet" description="Logs will appear as users perform actions." />
        </div>
      </div>
    </DashboardLayout>
  );
}
