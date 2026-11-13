"use client";

import { useCallback, useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { reportApi, type DailyReport } from "@/services/reports";
import { CardSkeleton } from "@/components/ui/Skeleton";
import EmptyState from "@/components/ui/EmptyState";
import { formatCurrency, cn, getStatusColor } from "@/lib/utils";
import {
  ArrowLeft,
  ArrowRight,
  Clock,
  IndianRupee,
  RotateCcw,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";

function todayIso(): string {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

function Stat({
  label,
  value,
  sub,
  icon,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  tone: "success" | "brand" | "warning" | "purple";
}) {
  const tones: Record<string, string> = {
    success: "bg-success-50 text-success-600",
    brand: "bg-brand-50 text-brand-600",
    warning: "bg-warning-50 text-warning-600",
    purple: "bg-purple-50 text-purple-600",
  };
  return (
    <div className="card flex items-start gap-4">
      <div className={cn("rounded-xl p-3", tones[tone])}>{icon}</div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-surface-500 uppercase tracking-wide">{label}</p>
        <p className="mt-1 text-2xl font-bold text-surface-900 tabular-nums">{value}</p>
        <p className="mt-0.5 text-xs text-surface-500">{sub}</p>
      </div>
    </div>
  );
}

export default function TodayCollectionPage() {
  const [date, setDate] = useState<string>(todayIso());
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await reportApi.getDailyReport(date));
    } catch (e) {
      console.error(e);
      setError("Could not load collections for this day.");
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    load();
  }, [load]);

  const shiftDate = (days: number) => {
    const d = new Date(date + "T00:00:00");
    d.setDate(d.getDate() + days);
    const off = d.getTimezoneOffset();
    setDate(new Date(d.getTime() - off * 60000).toISOString().slice(0, 10));
  };

  const fmt = (v: number | string | null | undefined) => formatCurrency(Number(v || 0));
  const pendingCount = report?.pending_details?.length || 0;

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">
              Collections
            </h1>
            <p className="mt-1 text-sm text-surface-500">
              Finance and Chitti money, kept separate
            </p>
          </div>

          <div className="flex items-center gap-2 rounded-2xl border border-surface-200 bg-white p-1.5 shadow-card">
            <button
              onClick={() => shiftDate(-1)}
              className="rounded-xl p-2 text-surface-500 hover:bg-surface-100 hover:text-surface-800 transition-colors"
              aria-label="Previous day"
            >
              <ArrowLeft size={16} />
            </button>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="bg-transparent text-sm font-semibold text-surface-800 outline-none cursor-pointer"
            />
            <button
              onClick={() => shiftDate(1)}
              className="rounded-xl p-2 text-surface-500 hover:bg-surface-100 hover:text-surface-800 transition-colors"
              aria-label="Next day"
            >
              <ArrowRight size={16} />
            </button>
            {date !== todayIso() && (
              <button
                onClick={() => setDate(todayIso())}
                className="ml-1 rounded-xl bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-100 transition-colors"
              >
                Today
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : error ? (
          <div className="card">
            <EmptyState icon="⚠️" title="Could not load" description={error} />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Collected"
                value={fmt(report?.collected_total)}
                sub={`${fmt(report?.finance_collected)} finance • ${fmt(report?.chitti_collected)} chitti`}
                icon={<TrendingUp size={20} />}
                tone="success"
              />
              <Stat
                label="Net of reversals"
                value={fmt(report?.net_collections)}
                sub={`${fmt(report?.reversals_total)} reversed`}
                icon={<IndianRupee size={20} />}
                tone="brand"
              />
              <Stat
                label="Due"
                value={fmt(report?.expected_total)}
                sub={`${fmt(report?.finance_expected)} finance • ${fmt(report?.chitti_expected)} chitti`}
                icon={<Clock size={20} />}
                tone="purple"
              />
              <Stat
                label="Pending"
                value={fmt(report?.pending_total)}
                sub={`${pendingCount} item${pendingCount === 1 ? "" : "s"} • ${fmt(report?.finance_pending)} finance / ${fmt(report?.chitti_pending)} chitti`}
                icon={<TrendingDown size={20} />}
                tone="warning"
              />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="card">
                <div className="flex items-center gap-2 mb-4">
                  <div className="rounded-xl bg-success-50 p-2 text-success-600">
                    <Wallet size={16} />
                  </div>
                  <h3 className="text-sm font-semibold text-surface-900">
                    Payments recorded
                  </h3>
                </div>
                {report && report.payments.length > 0 ? (
                  <div className="table-container">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Customer</th>
                          <th>Source</th>
                          <th>Method</th>
                          <th>By</th>
                          <th className="text-right">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.payments.map((p) => (
                          <tr key={`${p.source}-${p.id}`}>
                            <td className="font-medium">{p.customer_name}</td>
                            <td>
                              <span
                                className={cn(
                                  "badge",
                                  p.source === "CHITTI"
                                    ? "bg-purple-50 text-purple-700"
                                    : "bg-brand-50 text-brand-700"
                                )}
                              >
                                {p.source}
                              </span>
                            </td>
                            <td>{p.payment_method?.replace(/_/g, " ")}</td>
                            <td className="text-surface-500">{p.collector_name}</td>
                            <td
                              className={cn(
                                "text-right font-semibold",
                                p.is_reversal ? "text-danger-600" : "text-success-600"
                              )}
                            >
                              {p.is_reversal ? "-" : ""}
                              {fmt(p.amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    icon="💳"
                    title="No payments on this day"
                    description="Collections appear here as soon as they are recorded."
                  />
                )}
              </div>

              <div className="card">
                <div className="flex items-center gap-2 mb-4">
                  <div className="rounded-xl bg-warning-50 p-2 text-warning-600">
                    <RotateCcw size={16} />
                  </div>
                  <h3 className="text-sm font-semibold text-surface-900">
                    Still pending ({pendingCount})
                  </h3>
                </div>
                {report && report.pending_details.length > 0 ? (
                  <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
                    {report.pending_details.map((p) => (
                      <div
                        key={`${p.source}-${p.reference_id}`}
                        className="flex items-center justify-between rounded-xl border border-surface-100 p-3"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-surface-900 truncate">
                            {p.customer_name || "—"}
                          </p>
                          <p className="text-xs text-surface-500">
                            {p.source} • {p.period_label}
                            {p.account_number ? ` • ${p.account_number}` : ""}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-bold text-warning-600">
                            {fmt(p.pending)}
                          </p>
                          <span className={cn("badge", getStatusColor(p.status))}>
                            {p.status.replace(/_/g, " ")}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon="✅"
                    title="Nothing pending"
                    description="Every due for this day is fully collected."
                  />
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
