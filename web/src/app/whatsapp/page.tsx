"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import EmptyState from "@/components/ui/EmptyState";
import { MessageCircle, Send, CheckCircle2, XCircle } from "lucide-react";

export default function WhatsAppPage() {
  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight">WhatsApp Integration</h1>
          <p className="mt-1 text-sm text-surface-500">Manage WhatsApp notifications and templates</p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="card flex items-center gap-4">
            <div className="rounded-xl bg-success-50 p-3 text-success-600"><Send size={20} /></div>
            <div><p className="text-xs font-medium text-surface-500 uppercase">Sent Today</p><p className="text-2xl font-bold text-surface-900">0</p></div>
          </div>
          <div className="card flex items-center gap-4">
            <div className="rounded-xl bg-brand-50 p-3 text-brand-600"><CheckCircle2 size={20} /></div>
            <div><p className="text-xs font-medium text-surface-500 uppercase">Delivery Rate</p><p className="text-2xl font-bold text-surface-900">—</p></div>
          </div>
          <div className="card flex items-center gap-4">
            <div className="rounded-xl bg-danger-50 p-3 text-danger-600"><XCircle size={20} /></div>
            <div><p className="text-xs font-medium text-surface-500 uppercase">Failed Today</p><p className="text-2xl font-bold text-surface-900">0</p></div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="rounded-xl bg-success-50 p-2.5 text-success-600"><MessageCircle size={18} /></div>
            <h3 className="text-sm font-semibold text-surface-900">Notification Templates</h3>
          </div>
          <div className="space-y-2">
            {["Payment Received", "Payment Due Reminder", "Payment Overdue", "Welcome Message"].map((t) => (
              <div key={t} className="flex items-center justify-between rounded-xl border border-surface-100 p-4 hover:border-surface-200 transition-colors">
                <span className="text-sm font-medium text-surface-900">{t}</span>
                <span className="badge-neutral">Configurable</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <EmptyState icon="📱" title="No messages yet" description="WhatsApp message log will appear here once the integration is configured." />
        </div>
      </div>
    </DashboardLayout>
  );
}
