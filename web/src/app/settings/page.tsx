"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import { Settings, Bell, CreditCard, MessageCircle } from "lucide-react";

export default function SettingsPage() {
  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-surface-500">Configure system preferences and notification rules</p>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Notification Settings */}
          <div className="card">
            <div className="flex items-center gap-3 mb-6">
              <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600"><Bell size={18} /></div>
              <h3 className="text-sm font-semibold text-surface-900">Notification Settings</h3>
            </div>
            <div className="space-y-5">
              {[
                { label: "Payment Confirmation", desc: "Send WhatsApp when payment is received", defaultChecked: true },
                { label: "Due Reminder", desc: "Remind customers 1 day before due date", defaultChecked: true },
                { label: "Overdue Reminder", desc: "Notify when installments are overdue", defaultChecked: true },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-surface-900">{item.label}</p>
                    <p className="text-xs text-surface-500">{item.desc}</p>
                  </div>
                  <label className="relative inline-flex cursor-pointer items-center">
                    <input type="checkbox" defaultChecked={item.defaultChecked} className="peer sr-only" />
                    <div className="h-6 w-11 rounded-full bg-surface-200 after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-all peer-checked:bg-brand-600 peer-checked:after:translate-x-full" />
                  </label>
                </div>
              ))}
            </div>
          </div>

          {/* Payment Settings */}
          <div className="card">
            <div className="flex items-center gap-3 mb-6">
              <div className="rounded-xl bg-success-50 p-2.5 text-success-600"><CreditCard size={18} /></div>
              <h3 className="text-sm font-semibold text-surface-900">Payment Settings</h3>
            </div>
            <div className="space-y-4">
              <div><label className="input-label">Advance Payment Policy</label><select className="input-field"><option value="AUTO_ALLOCATE">Auto-allocate to future installments</option><option value="HOLD_AS_CREDIT">Hold as credit balance</option></select></div>
              <div><label className="input-label">Business Timezone</label><input type="text" value="Asia/Kolkata" disabled className="input-field bg-surface-50" /></div>
            </div>
          </div>

          {/* WhatsApp Configuration */}
          <div className="card lg:col-span-2">
            <div className="flex items-center gap-3 mb-6">
              <div className="rounded-xl bg-success-50 p-2.5 text-success-600"><MessageCircle size={18} /></div>
              <h3 className="text-sm font-semibold text-surface-900">WhatsApp Business Configuration</h3>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div><label className="input-label">Phone Number ID</label><input type="text" className="input-field" placeholder="Set via environment variable" disabled /></div>
              <div><label className="input-label">Business Account ID</label><input type="text" className="input-field" placeholder="Set via environment variable" disabled /></div>
            </div>
            <p className="mt-3 text-xs text-surface-400">WhatsApp credentials are configured via environment variables for security.</p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
