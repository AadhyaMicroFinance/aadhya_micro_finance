"use client";

import { useState, useEffect, useCallback } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { useAuthStore } from "@/hooks/useAuth";
import { CardSkeleton } from "@/components/ui/Skeleton";
import EmptyState from "@/components/ui/EmptyState";
import Avatar from "@/components/ui/Avatar";
import { reportApi, type DailyReport } from "@/services/reports";
import { formatCurrency, cn } from "@/lib/utils";
import {
  CalendarDays,
  TrendingUp,
  TrendingDown,
  Wallet,
  Clock,
  Users,
  ArrowLeft,
  ArrowRight,
  IndianRupee,
  RotateCcw,
  CreditCard,
} from "lucide-react";

function todayIso(): string {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

// A single premium gradient KPI card
function GradientStat({
  label,
  value,
  sub,
  icon,
  gradient,
  ring,
  onClick,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  gradient: string;
  ring?: string;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "relative overflow-hidden rounded-3xl p-[1.5px] shadow-elevated transition-transform duration-200",
        onClick && "cursor-pointer hover:-translate-y-1",
        ring
      )}
    >
      <div className={cn("relative rounded-[1.35rem] p-5 h-full", gradient)}>
        {/* glass shine */}
        <div className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-white/20 blur-2xl" />
        <div className="pointer-events-none absolute -left-10 -bottom-10 h-24 w-24 rounded-full bg-white/10 blur-2xl" />
        <div className="relative flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-white/80">
              {label}
            </p>
            <p className="text-2xl font-bold text-white tabular-nums tracking-tight">
              {value}
            </p>
            {sub && <p className="text-xs font-medium text-white/75">{sub}</p>}
          </div>
          <div className="rounded-2xl bg-white/20 p-2.5 text-white backdrop-blur-sm">
            {icon}
          </div>
        </div>
        {onClick && (
          <div className="relative mt-3 text-[11px] font-semibold text-white/90">
            Click to view details →
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuthStore();
  const [loading, setLoading] = useState(true);
  const [report, setReport] = useState<DailyReport | null>(null);
  const [date, setDate] = useState<string>(todayIso());
  const [showPending, setShowPending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await reportApi.getDailyReport(date);
      setReport(data);
    } catch (e) {
      console.error(e);
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

  const greeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  };

  const fmt = (v: string | number) => formatCurrency(Number(v || 0));
  const pendingCount = report?.pending_details?.length || 0;

  return (
    <DashboardLayout>
      <div className="space-y-8">
        {/* Header + Calendar */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">
              {greeting()}, {user?.full_name?.split(" ")[0] || "User"} 👋
            </h1>
            <p className="mt-1 text-sm text-surface-500">
              Your day&apos;s collection overview
            </p>
          </div>

          {/* Calendar control */}
          <div className="flex items-center gap-2 rounded-2xl border border-surface-200 bg-white p-1.5 shadow-card">
            <button
              onClick={() => shiftDate(-1)}
              className="rounded-xl p-2 text-surface-500 hover:bg-surface-100 hover:text-surface-800 transition-colors"
              aria-label="Previous day"
            >
              <ArrowLeft size={16} />
            </button>
            <div className="relative flex items-center gap-2 px-1">
              <CalendarDays size={16} className="text-brand-600" />
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="bg-transparent text-sm font-semibold text-surface-800 outline-none cursor-pointer"
              />
            </div>
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

        {/* KPI cards */}
        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <GradientStat
              label="Expected Today"
              value={fmt(report?.expected_total || 0)}
              sub={`${report?.expected_count || 0} dues scheduled`}
              icon={<Clock size={20} />}
              gradient="bg-gradient-to-br from-brand-500 via-brand-600 to-indigo-600"
            />
            <GradientStat
              label="Collected Today"
              value={fmt(report?.collected_total || 0)}
              sub={`${fmt(report?.finance_collected || 0)} finance • ${fmt(report?.chitti_collected || 0)} chitti`}
              icon={<Wallet size={20} />}
              gradient="bg-gradient-to-br from-success-500 via-emerald-600 to-teal-600"
            />
            <GradientStat
              label="Net Collections"
              value={fmt(report?.net_collections || 0)}
              sub={
                Number(report?.reversals_total || 0) > 0
                  ? `${fmt(Number(report?.reversals_total || 0))} reversed`
                  : "after reversals"
              }
              icon={<IndianRupee size={20} />}
              gradient="bg-gradient-to-br from-indigo-500 via-purple-600 to-fuchsia-600"
            />
            <GradientStat
              label="Pending Today"
              value={fmt(report?.pending_total || 0)}
              sub={`${pendingCount} pending item${pendingCount !== 1 ? "s" : ""}`}
              icon={<TrendingDown size={20} />}
              gradient="bg-gradient-to-br from-warning-500 via-orange-500 to-amber-600"
              ring="hover:shadow-[0_10px_30px_-6px_rgb(245_158_11_0.5)]"
              onClick={() => setShowPending(true)}
            />
          </div>
        )}

        {/* Collection rate + reversals strip */}
        {!loading && report && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="card lg:col-span-2">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-surface-900">
                  Collection Rate
                </h3>
                <span className="text-sm font-bold text-brand-600">
                  {report.collection_rate}%
                </span>
              </div>
              <div className="h-3 w-full rounded-full bg-surface-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-brand-500 to-indigo-500 transition-all duration-700"
                  style={{
                    width: `${Math.min(report.collection_rate, 100)}%`,
                  }}
                />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3 text-center">
                <div className="rounded-xl bg-brand-50 p-3">
                  <p className="text-[11px] font-medium text-brand-600 uppercase">
                    Finance due
                  </p>
                  <p className="text-sm font-bold text-brand-700">
                    {fmt(report.finance_expected)}
                  </p>
                </div>
                <div className="rounded-xl bg-purple-50 p-3">
                  <p className="text-[11px] font-medium text-purple-600 uppercase">
                    Chitti due
                  </p>
                  <p className="text-sm font-bold text-purple-700">
                    {fmt(report.chitti_expected)}
                  </p>
                </div>
                <div className="rounded-xl bg-danger-50 p-3">
                  <p className="text-[11px] font-medium text-danger-600 uppercase">
                    Reversals
                  </p>
                  <p className="text-sm font-bold text-danger-700">
                    {fmt(report.reversals_total)}
                  </p>
                </div>
              </div>
              {/* Collected is split per stream: finance and chitti money are
                  separate ledgers and must never be blended into one number
                  without showing which is which. */}
              <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                <div className="rounded-xl bg-success-50 p-3">
                  <p className="text-[11px] font-medium text-success-600 uppercase">
                    Finance collected
                  </p>
                  <p className="text-sm font-bold text-success-700">
                    {fmt(report.finance_collected)}
                  </p>
                </div>
                <div className="rounded-xl bg-purple-50 p-3">
                  <p className="text-[11px] font-medium text-purple-600 uppercase">
                    Chitti collected
                  </p>
                  <p className="text-sm font-bold text-purple-700">
                    {fmt(report.chitti_collected)}
                  </p>
                </div>
                <div className="rounded-xl bg-surface-50 p-3">
                  <p className="text-[11px] font-medium text-surface-500 uppercase">
                    Total
                  </p>
                  <p className="text-sm font-bold text-surface-800">
                    {fmt(report.collected_total)}
                  </p>
                </div>
              </div>
            </div>

            {/* Payment methods */}
            <div className="card">
              <h3 className="text-sm font-semibold text-surface-900 mb-3">
                By Method
              </h3>
              {report.by_method.length === 0 ? (
                <p className="text-sm text-surface-500">No collections yet.</p>
              ) : (
                <div className="space-y-3">
                  {report.by_method.map((m) => (
                    <div
                      key={m.method}
                      className="flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <div className="rounded-lg bg-brand-50 p-1.5 text-brand-600">
                          <CreditCard size={14} />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-surface-800">
                            {m.method.replace("_", " ")}
                          </p>
                          <p className="text-xs text-surface-400">
                            {m.count} payment{m.count !== 1 ? "s" : ""}
                          </p>
                        </div>
                      </div>
                      <span className="text-sm font-bold text-surface-900">
                        {fmt(m.total)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Collections by user + Payments */}
        {!loading && report && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Collections by user */}
            <div className="card">
              <div className="flex items-center gap-2 mb-4">
                <div className="rounded-xl bg-brand-50 p-2 text-brand-600">
                  <Users size={16} />
                </div>
                <h3 className="text-sm font-semibold text-surface-900">
                  Collections by User
                </h3>
              </div>
              {report.by_user.length === 0 ? (
                <EmptyState
                  icon="🧑‍💼"
                  title="No collections today"
                  description="Collections will appear here grouped by the collector."
                />
              ) : (
                <div className="space-y-3">
                  {report.by_user.map((u) => {
                    const max = Math.max(
                      ...report.by_user.map((x) => Number(x.collected_total)),
                      1
                    );
                    const pct = (Number(u.collected_total) / max) * 100;
                    return (
                      <div
                        key={u.user_id || u.username}
                        className="rounded-2xl border border-surface-100 p-4 hover:border-brand-200 hover:shadow-sm transition-all"
                      >
                        <div className="flex items-center gap-3">
                          <Avatar name={u.full_name} size="md" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-surface-900 truncate">
                              {u.full_name}
                            </p>
                            <p className="text-xs text-surface-500">
                              {u.role.replace("_", " ")} • {u.payment_count}{" "}
                              payment{u.payment_count !== 1 ? "s" : ""}
                            </p>
                          </div>
                          <span className="text-sm font-bold text-success-600">
                            {fmt(u.collected_total)}
                          </span>
                        </div>
                        <div className="mt-3 h-1.5 w-full rounded-full bg-surface-100 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-success-400 to-emerald-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Day's payments */}
            <div className="card">
              <div className="flex items-center gap-2 mb-4">
                <div className="rounded-xl bg-success-50 p-2 text-success-600">
                  <TrendingUp size={16} />
                </div>
                <h3 className="text-sm font-semibold text-surface-900">
                  Payments This Day
                </h3>
              </div>
              {report.payments.length === 0 ? (
                <EmptyState
                  icon="💳"
                  title="No payments"
                  description="Payments recorded for this day will appear here."
                />
              ) : (
                <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
                  {report.payments.map((p) => (
                    <div
                      key={p.id}
                      className={cn(
                        "flex items-center justify-between rounded-xl border p-3",
                        p.is_reversal
                          ? "border-danger-100 bg-danger-50/50"
                          : "border-surface-100"
                      )}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div
                          className={cn(
                            "rounded-lg p-2",
                            p.is_reversal
                              ? "bg-danger-100 text-danger-600"
                              : "bg-success-50 text-success-600"
                          )}
                        >
                          {p.is_reversal ? (
                            <RotateCcw size={14} />
                          ) : (
                            <Wallet size={14} />
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-surface-900 truncate">
                            {p.customer_name}
                          </p>
                          <p className="text-xs text-surface-500">
                            {p.source} • by {p.collector_name}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p
                          className={cn(
                            "text-sm font-bold",
                            p.is_reversal ? "text-danger-600" : "text-surface-900"
                          )}
                        >
                          {p.is_reversal ? "-" : ""}
                          {fmt(p.amount)}
                        </p>
                        <span
                          className={cn(
                            "text-[10px] font-semibold px-2 py-0.5 rounded-full",
                            p.status === "COMPLETED"
                              ? "bg-success-50 text-success-700"
                              : "bg-danger-50 text-danger-700"
                          )}
                        >
                          {p.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Pending details modal */}
      {showPending && report && (
        <div
          className="modal-backdrop"
          onClick={() => setShowPending(false)}
        >
          <div
            className="modal-content max-w-3xl max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-surface-100 bg-white px-6 py-4">
              <div>
                <h3 className="text-lg font-bold text-surface-900">
                  Pending Details
                </h3>
                <p className="text-xs text-surface-500">
                  Due on {report.date} • {pendingCount} item
                  {pendingCount !== 1 ? "s" : ""}
                </p>
              </div>
              <button
                onClick={() => setShowPending(false)}
                className="rounded-lg p-2 text-surface-400 hover:bg-surface-100 transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="p-6">
              {pendingCount === 0 ? (
                <EmptyState
                  icon="✅"
                  title="Nothing pending"
                  description="All dues for this day are fully collected."
                />
              ) : (
                <div className="space-y-3">
                  {report.pending_details.map((p) => (
                    <div
                      key={`${p.source}-${p.reference_id}`}
                      className="rounded-2xl border border-surface-100 p-4 hover:border-warning-200 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div
                            className={cn(
                              "rounded-xl p-2",
                              p.source === "CHITTI"
                                ? "bg-purple-50 text-purple-600"
                                : "bg-brand-50 text-brand-600"
                            )}
                          >
                            <Wallet size={16} />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-surface-900">
                              {p.customer_name || "—"}
                            </p>
                            <p className="text-xs text-surface-500">
                              {p.source} • {p.period_label}
                              {p.account_number ? ` • ${p.account_number}` : ""}
                            </p>
                            {p.mobile_number && (
                              <p className="text-xs text-surface-400">
                                📞 {p.mobile_number}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-lg font-bold text-warning-600">
                            {fmt(p.pending)}
                          </p>
                          <p className="text-xs text-surface-400">
                            of {fmt(p.expected)} due
                          </p>
                        </div>
                      </div>
                      <div className="mt-3 h-1.5 w-full rounded-full bg-surface-100 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-warning-400 to-orange-500"
                          style={{
                            width: `${Math.min(
                              (Number(p.paid) / Math.max(Number(p.expected), 1)) *
                                100,
                              100
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
