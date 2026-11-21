"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { DonutChart, GroupedBarChart, LineChart } from "@/components/charts/Charts";
import { CardSkeleton } from "@/components/ui/Skeleton";
import EmptyState from "@/components/ui/EmptyState";
import { financeApi } from "@/services/finance";
import { getApiErrorMessage } from "@/services/api-client";
import { cn, formatCurrency, formatDate, getStatusColor } from "@/lib/utils";
import type { FinanceDashboardData } from "@/types";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CircleDollarSign,
  Clock,
  IndianRupee,
  Layers,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";

type LooseRecord = Record<string, unknown>;

function asRecord(value: unknown): LooseRecord {
  return value && typeof value === "object" ? (value as LooseRecord) : {};
}

function pickText(row: LooseRecord, keys: string[], fallback = "—"): string {
  for (const key of keys) {
    const value = row[key];
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return fallback;
}

function pickNumber(row: LooseRecord, keys: string[]): number {
  for (const key of keys) {
    const value = row[key];
    if (value === null || value === undefined || value === "") continue;
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function pickDateLabel(row: LooseRecord, keys: string[]): string {
  const raw = pickText(row, keys, "");
  if (!raw) return "—";
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? raw : formatDate(raw);
}

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: "#22c55e",
  COMPLETED: "#16a34a",
  CLOSED: "#64748b",
  DEFAULTED: "#ef4444",
  OVERDUE: "#ef4444",
  PENDING: "#f59e0b",
  PARTIALLY_PAID: "#6366f1",
  SUSPENDED: "#f97316",
  DRAFT: "#94a3b8",
};

function statusColor(status: string): string {
  return STATUS_COLORS[status.toUpperCase().replace(/[\s-]+/g, "_")] ?? "#94a3b8";
}

function KpiCard({
  label,
  value,
  sub,
  icon,
  gradient,
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  gradient: string;
}) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl bg-gradient-to-br p-5 shadow-elevated transition-transform duration-200 hover:-translate-y-0.5",
        gradient
      )}
    >
      <div className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-white/20 blur-2xl" />
      <div className="pointer-events-none absolute -bottom-12 -left-6 h-24 w-24 rounded-full bg-black/10 blur-2xl" />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-white/80">
            {label}
          </p>
          <p className="truncate text-xl font-bold leading-tight text-white tabular-nums">
            {value}
          </p>
        </div>
        <div className="flex-shrink-0 rounded-xl bg-white/20 p-2 text-white backdrop-blur-sm">
          {icon}
        </div>
      </div>
      <p className="relative mt-3 text-[11px] font-medium text-white/85">{sub}</p>
    </div>
  );
}

function SectionHeader({
  icon,
  title,
  hint,
  href,
  linkLabel,
}: {
  icon: React.ReactNode;
  title: string;
  hint?: string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
      <div className="flex items-start gap-2.5">
        <span className="rounded-xl bg-brand-50 p-2 text-brand-600">{icon}</span>
        <div>
          <h3 className="text-sm font-semibold text-surface-900">{title}</h3>
          {hint && <p className="mt-0.5 text-[11px] text-surface-500">{hint}</p>}
        </div>
      </div>
      {href && linkLabel && (
        <Link href={href} className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700">
          {linkLabel} <ArrowRight size={12} />
        </Link>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return <span className={cn("badge", getStatusColor(status))}>{status.replace(/_/g, " ")}</span>;
}

export default function FinanceDashboardPage() {
  const [data, setData] = useState<FinanceDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await financeApi.dashboard());
    } catch (e) {
      setData(null);
      setError(getApiErrorMessage(e, "Could not load the Finance dashboard."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const repaymentTrend = useMemo(
    () =>
      (data?.trends ?? []).map((point) => ({
        period: point.period,
        expected: Number(point.expected || 0),
        collected: Number(point.collected || 0),
      })),
    [data]
  );

  const collectionTrend = useMemo(
    () =>
      (data?.trends ?? []).map((point) => {
        const expected = Number(point.expected || 0);
        const collected = Number(point.collected || 0);
        return {
          period: point.period,
          collected,
          shortfall: Math.max(expected - collected, 0),
        };
      }),
    [data]
  );

  const statusDistribution = useMemo(
    () =>
      (data?.status_distribution ?? []).map((row) => ({
        label: row.status.replace(/_/g, " "),
        value: Number(row.count || 0),
        color: statusColor(row.status),
      })),
    [data]
  );

  const kpis = data?.kpis;

  if (loading) {
    return (
      <DashboardLayout>
        <div className="space-y-6">
          <div className="space-y-2">
            <div className="skeleton h-8 w-56" />
            <div className="skeleton h-4 w-80" />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <CardSkeleton />
            <CardSkeleton />
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-7">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-xl bg-brand-50 p-2 text-brand-600">
                <TrendingUp size={18} />
              </span>
              <h1 className="text-xl font-bold tracking-tight text-surface-900 sm:text-2xl">
                Finance Dashboard
              </h1>
            </div>
            <p className="mt-1.5 text-sm text-surface-500">
              Finance-only lending health, repayment trends and collection activity.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/finance/collections" className="btn-secondary btn-sm">
              <CircleDollarSign size={14} />
              Collections
            </Link>
            <Link href="/finance" className="btn-secondary btn-sm">
              All Finances <ArrowRight size={14} />
            </Link>
            <button type="button" onClick={() => void load()} className="btn-secondary btn-sm">
              <RefreshCw size={14} />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
            <AlertTriangle size={16} />
            <span className="flex-1">{error}</span>
            <button type="button" onClick={() => void load()} className="btn-secondary btn-sm">
              Retry
            </button>
          </div>
        )}

        {!data ? (
          <div className="card">
            <EmptyState
              icon="📊"
              title="No Finance data available"
              description="Dashboard data will appear once the Finance service responds successfully."
              action={<button type="button" onClick={() => void load()} className="btn-secondary">Try again</button>}
            />
          </div>
        ) : !kpis || kpis.total_accounts === 0 ? (
          <div className="card">
            <EmptyState
              icon="💰"
              title="No Finance accounts yet"
              description="Create a loan account to start tracking disbursements, collections and repayments."
              action={
                <Link href="/finance" className="btn-primary">
                  View All Finances <ArrowRight size={16} />
                </Link>
              }
            />
          </div>
        ) : (
          <>
            {/* KPI cards — Finance only */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <KpiCard
                label="Total Finance Accounts"
                value={Number(kpis.total_accounts || 0).toLocaleString("en-IN")}
                sub={`${statusDistribution.length} status buckets tracked`}
                icon={<Wallet size={18} />}
                gradient="from-brand-500 via-brand-600 to-indigo-600"
              />
              <KpiCard
                label="Total Principal Disbursed"
                value={formatCurrency(kpis.total_principal_disbursed)}
                sub="Principal lent across all accounts"
                icon={<IndianRupee size={18} />}
                gradient="from-violet-500 via-purple-600 to-fuchsia-600"
              />
              <KpiCard
                label="Total Outstanding"
                value={formatCurrency(kpis.total_outstanding)}
                sub="Yet to be collected"
                icon={<TrendingDown size={18} />}
                gradient="from-sky-500 via-blue-600 to-indigo-600"
              />
              <KpiCard
                label="Total Collections"
                value={formatCurrency(kpis.total_collections)}
                sub="Repayments collected to date"
                icon={<CircleDollarSign size={18} />}
                gradient="from-emerald-500 via-emerald-600 to-teal-600"
              />
              <KpiCard
                label="Pending Repayments"
                value={Number(kpis.pending_repayments || 0).toLocaleString("en-IN")}
                sub="Installments awaiting payment"
                icon={<Clock size={18} />}
                gradient="from-amber-500 via-orange-500 to-orange-600"
              />
              <KpiCard
                label="Overdue Repayments"
                value={Number(kpis.overdue_repayments || 0).toLocaleString("en-IN")}
                sub="Past their scheduled due date"
                icon={<AlertTriangle size={18} />}
                gradient="from-rose-500 via-rose-600 to-red-600"
              />
            </div>

            {/* Trends + distribution */}
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <div className="card">
                <SectionHeader
                  icon={<TrendingUp size={15} />}
                  title="Repayment Trends"
                  hint="Expected versus actually collected, by period"
                />
                <LineChart
                  data={repaymentTrend}
                  series={[
                    { key: "expected", label: "Expected", color: "#94a3b8", dashed: true },
                    { key: "collected", label: "Collected", color: "#4f46e5", fill: true },
                  ]}
                  height={245}
                  xLabel={(row) => String(row.period)}
                />
              </div>

              <div className="card">
                <SectionHeader
                  icon={<CircleDollarSign size={15} />}
                  title="Collection Trends"
                  hint="Collected amount versus outstanding shortfall"
                />
                <GroupedBarChart
                  data={collectionTrend}
                  series={[
                    { key: "collected", label: "Collected", color: "#10b981" },
                    { key: "shortfall", label: "Shortfall", color: "#fcd34d" },
                  ]}
                  height={245}
                  xLabel={(row) => String(row.period)}
                />
              </div>

              <div className="card lg:col-span-2">
                <SectionHeader
                  icon={<Layers size={15} />}
                  title="Account Status Distribution"
                  hint="All Finance accounts grouped by current status"
                />
                {statusDistribution.length ? (
                  <DonutChart
                    data={statusDistribution}
                    centerLabel="Accounts"
                    formatter={(value) => String(Math.round(value))}
                  />
                ) : (
                  <EmptyState icon="🧾" title="No status data" description="Statuses appear once accounts are created." />
                )}
              </div>
            </div>

            {/* Activity feeds */}
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
              <div className="card">
                <SectionHeader
                  icon={<Activity size={15} />}
                  title="Recent Finance Activity"
                  hint="Latest ledger events"
                />
                {data.recent_activity.length ? (
                  <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                    {data.recent_activity.slice(0, 8).map((item, index) => {
                      const row = asRecord(item);
                      const description = pickText(row, ["description", "activity_type", "event_type", "type"], "Activity");
                      const customer = pickText(row, ["customer_name", "customer"], "");
                      const account = pickText(row, ["account_number", "account_code"], "");
                      const when = pickDateLabel(row, ["created_at", "date", "payment_date"]);
                      const amount = pickNumber(row, ["amount", "total", "value"]);
                      const status = pickText(row, ["status"], "");
                      return (
                        <div key={String(row.id ?? row.transaction_id ?? index)} className="rounded-xl border border-surface-100 p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-surface-900">{description}</p>
                              <p className="mt-0.5 truncate text-[11px] text-surface-500">
                                {[customer, account].filter(Boolean).join(" · ") || when}
                              </p>
                              <p className="mt-0.5 text-[11px] text-surface-400">{when}</p>
                            </div>
                            <div className="flex-shrink-0 text-right">
                              {amount > 0 && (
                                <p className="text-sm font-bold tabular-nums text-surface-900">
                                  {formatCurrency(amount)}
                                </p>
                              )}
                              {status && <StatusPill status={status} />}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <EmptyState icon="🕒" title="No recent activity" description="New Finance events will show up here." />
                )}
              </div>

              <div className="card">
                <SectionHeader
                  icon={<CalendarClock size={15} />}
                  title="Upcoming Repayments"
                  hint="Next scheduled installments"
                  href="/finance/collections"
                  linkLabel="View collections"
                />
                {data.upcoming_repayments.length ? (
                  <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                    {data.upcoming_repayments.slice(0, 8).map((item, index) => {
                      const row = asRecord(item);
                      const customer = pickText(row, ["customer_name", "customer"]);
                      const account = pickText(row, ["account_number", "account_code"], "");
                      const installment = pickNumber(row, ["installment_number", "period_number"]);
                      const due = pickDateLabel(row, ["due_date", "next_due_date"]);
                      const amount = pickNumber(row, ["expected_amount", "remaining_amount", "amount_due", "pending_amount", "outstanding_amount"]);
                      const status = pickText(row, ["status"], "");
                      return (
                        <div key={String(row.id ?? row.schedule_id ?? index)} className="rounded-xl border border-surface-100 p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-surface-900">{customer}</p>
                              <p className="mt-0.5 truncate text-[11px] text-surface-500">
                                {[account, installment ? `Installment #${installment}` : ""].filter(Boolean).join(" · ") || "Scheduled installment"}
                              </p>
                              <p className="mt-0.5 text-[11px] text-surface-400">Due {due}</p>
                            </div>
                            <p className="flex-shrink-0 text-sm font-bold tabular-nums text-surface-900">
                              {formatCurrency(amount)}
                            </p>
                          </div>
                          {status && <div className="mt-2"><StatusPill status={status} /></div>}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <EmptyState icon="✅" title="Nothing upcoming" description="No repayments are scheduled ahead." />
                )}
              </div>

              <div className="card">
                <SectionHeader
                  icon={<AlertTriangle size={15} />}
                  title="Overdue Accounts"
                  hint="Accounts with missed installments"
                  href="/finance/collections"
                  linkLabel="Collect now"
                />
                {data.overdue_accounts.length ? (
                  <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                    {data.overdue_accounts.slice(0, 8).map((item, index) => {
                      const row = asRecord(item);
                      const customer = pickText(row, ["customer_name", "customer"]);
                      const account = pickText(row, ["account_number", "account_code"], "");
                      const days = pickNumber(row, ["days_overdue"]);
                      const amount = pickNumber(row, ["overdue_amount", "amount_overdue", "pending_amount", "outstanding_amount"]);
                      const status = pickText(row, ["status"], "OVERDUE");
                      return (
                        <div key={String(row.id ?? row.finance_account_id ?? index)} className="rounded-xl border border-danger-100 bg-danger-50/40 p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-surface-900">{customer}</p>
                              <p className="mt-0.5 truncate text-[11px] text-surface-500">{account || "Finance account"}</p>
                              <p className="mt-0.5 text-[11px] font-medium text-danger-600">
                                {days > 0 ? `${days} day${days === 1 ? "" : "s"} overdue` : "Payment overdue"}
                              </p>
                            </div>
                            <p className="flex-shrink-0 text-sm font-bold tabular-nums text-danger-600">
                              {formatCurrency(amount)}
                            </p>
                          </div>
                          <div className="mt-2"><StatusPill status={status} /></div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <EmptyState icon="🎉" title="No overdue accounts" description="Every account is on schedule." />
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
