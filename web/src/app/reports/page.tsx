"use client";

import { useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { cn } from "@/lib/utils";
import EmptyState from "@/components/ui/EmptyState";
import { Calendar, Download, FileText } from "lucide-react";

const reportTypes = [
  { id: "daily", label: "Daily Collection", icon: "📅" },
  { id: "weekly", label: "Weekly Collection", icon: "📊" },
  { id: "monthly", label: "Monthly Collection", icon: "📈" },
  { id: "outstanding", label: "Outstanding Report", icon: "💰" },
  { id: "overdue", label: "Overdue Report", icon: "⚠️" },
  { id: "finance", label: "Finance Report", icon: "💼" },
  { id: "chitti", label: "Chitti Report", icon: "🤝" },
  { id: "collector", label: "Collector Report", icon: "👤" },
  { id: "payment-method", label: "Payment Method Report", icon: "💳" },
];

export default function ReportsPage() {
  const [selectedReport, setSelectedReport] = useState("daily");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Reports</h1>
          <p className="mt-1 text-sm text-surface-500">Generate and export financial reports</p>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          {/* Report Type Selector */}
          <div className="card lg:col-span-1">
            <h3 className="text-xs font-bold uppercase tracking-wider text-surface-500 mb-4">Report Type</h3>
            <div className="space-y-1">
              {reportTypes.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setSelectedReport(r.id)}
                  className={cn(
                    "w-full rounded-xl p-3 text-left text-sm font-medium transition-all",
                    selectedReport === r.id
                      ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200"
                      : "text-surface-600 hover:bg-surface-50"
                  )}
                >
                  <span className="mr-2">{r.icon}</span>
                  {r.label}
                </button>
              ))}
            </div>
          </div>

          {/* Report Area */}
          <div className="card lg:col-span-3">
            <h3 className="text-sm font-semibold text-surface-900 mb-4">
              {reportTypes.find((r) => r.id === selectedReport)?.label}
            </h3>

            <div className="flex gap-4 mb-6">
              <div className="flex items-center gap-2">
                <Calendar size={16} className="text-surface-400" />
                <div>
                  <label className="input-label">From</label>
                  <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input-field" />
                </div>
              </div>
              <div>
                <label className="input-label">To</label>
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="input-field" />
              </div>
              <div className="flex items-end">
                <button className="btn-primary"><FileText size={16} /> Generate</button>
              </div>
            </div>

            <EmptyState icon="📊" title="No data yet" description="Select date range and click Generate to view report data." />

            <div className="flex gap-3 mt-6">
              <button className="btn-secondary btn-sm"><Download size={14} /> Export CSV</button>
              <button className="btn-secondary btn-sm"><Download size={14} /> Export Excel</button>
              <button className="btn-secondary btn-sm"><Download size={14} /> Export PDF</button>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
