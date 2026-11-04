"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import EmptyState from "@/components/ui/EmptyState";
import { TrendingUp, TrendingDown, Clock } from "lucide-react";

export default function TodayCollectionPage() {
  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Today&apos;s Collections</h1>
          <p className="mt-1 text-sm text-surface-500">Real-time view of today&apos;s payment collections</p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="card flex items-center gap-4">
            <div className="rounded-xl bg-success-50 p-3 text-success-600"><TrendingUp size={20} /></div>
            <div><p className="text-xs font-medium text-surface-500 uppercase">Collected Today</p><p className="text-2xl font-bold text-surface-900">₹0</p></div>
          </div>
          <div className="card flex items-center gap-4">
            <div className="rounded-xl bg-brand-50 p-3 text-brand-600"><Clock size={20} /></div>
            <div><p className="text-xs font-medium text-surface-500 uppercase">Expected Today</p><p className="text-2xl font-bold text-surface-900">₹0</p></div>
          </div>
          <div className="card flex items-center gap-4">
            <div className="rounded-xl bg-warning-50 p-3 text-warning-600"><TrendingDown size={20} /></div>
            <div><p className="text-xs font-medium text-surface-500 uppercase">Pending Today</p><p className="text-2xl font-bold text-surface-900">₹0</p></div>
          </div>
        </div>

        <div className="card">
          <EmptyState icon="📋" title="No collections today" description="Collections will appear here as payments are recorded." />
        </div>
      </div>
    </DashboardLayout>
  );
}
