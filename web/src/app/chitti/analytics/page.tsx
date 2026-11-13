"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  analyticsApi,
  type ChittiOverview,
  type MemberPaymentRow,
} from "@/services/analytics";
import { LineChart, GroupedBarChart, DonutChart } from "@/components/charts/Charts";
import { formatCurrency, cn } from "@/lib/utils";
import { CardSkeleton } from "@/components/ui/Skeleton";
import EmptyState from "@/components/ui/EmptyState";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Clock,
  CreditCard,
  Download,
  Eye,
  Handshake,
  IndianRupee,
  Landmark,
  Percent,
  RefreshCw,
  Search,
  Smartphone,
  TrendingDown,
  TrendingUp,
  Users,
  Wallet,
  X,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const METHOD_ICON: Record<string, React.ReactNode> = {
  CASH: <Banknote size={15} />,
  UPI: <Smartphone size={15} />,
  BANK_TRANSFER: <Landmark size={15} />,
  OTHER: <CreditCard size={15} />,
};

const METHOD_LABEL: Record<string, string> = {
  CASH: "Cash",
  UPI: "UPI",
  BANK_TRANSFER: "Bank Transfer",
  OTHER: "Other",
};

const STATUS_CLASS: Record<string, string> = {
  PAID: "badge-success",
  PARTIALLY_PAID: "badge-info",
  PENDING: "badge-warning",
  OVERDUE: "badge-danger",
  ADVANCE_PAID: "badge-brand",
};

const PRESETS = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "this_month", label: "This month" },
  { key: "last_month", label: "Last month" },
] as const;

/** Business date (IST), independent of the operator's machine timezone. */
function istTodayIso(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function shiftIso(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function presetRange(key: string): { start: string; end: string } {
  const today = istTodayIso();
  const [year, month] = today.split("-").map(Number);
  const monthStr = String(month).padStart(2, "0");
  switch (key) {
    case "today":
      return { start: today, end: today };
    case "yesterday": {
      const y = shiftIso(today, -1);
      return { start: y, end: y };
    }
    case "7d":
      return { start: shiftIso(today, -6), end: today };
    case "this_month":
      return { start: `${year}-${monthStr}-01`, end: today };
    case "last_month": {
      const startMonth = month === 1 ? 12 : month - 1;
      const startYear = month === 1 ? year - 1 : year;
      const lastDay = new Date(Date.UTC(year, month - 1, 0)).getUTCDate();
      return {
        start: `${startYear}-${String(startMonth).padStart(2, "0")}-01`,
        end: `${year}-${monthStr}-${String(lastDay).padStart(2, "0")}`,
      };
    }
    default:
      return { start: shiftIso(today, -29), end: today };
  }
}

function exportCsv(
  filename: string,
  headers: string[],
  rows: (string | number | null | undefined)[][]
) {
  const escape = (value: string | number | null | undefined) =>
    `"${String(value ?? "").replace(/"/g, '""')}"`;
  const csv = [headers.map(escape).join(","), ...rows.map((r) => r.map(escape).join(","))].join(
    "\n"
  );
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Small components
// ---------------------------------------------------------------------------

function KpiCard({
  label,
  value,
  sub,
  icon,
  gradient,
  onClick,
}: {
  label: string;
  value: string;
  sub?: React.ReactNode;
  icon: React.ReactNode;
  gradient: string;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "group relative overflow-hidden rounded-2xl bg-gradient-to-br p-5 shadow-elevated transition-all duration-200",
        gradient,
        onClick && "cursor-pointer hover:-translate-y-0.5 hover:shadow-modal"
      )}
    >
      <div className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-white/20 blur-2xl" />
      <div className="pointer-events-none absolute -bottom-12 -left-6 h-24 w-24 rounded-full bg-black/10 blur-2xl" />
      <div className="relative flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-white/80">
            {label}
          </p>
          <p className="text-xl font-bold leading-tight text-white">{value}</p>
        </div>
        <div className="rounded-xl bg-white/20 p-2 text-white backdrop-blur-sm">{icon}</div>
      </div>
      {sub && <div className="relative mt-3 text-[11px] font-medium text-white/85">{sub}</div>}
    </div>
  );
}

function MiniStat({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  tone: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-surface-100 bg-white p-3">
      <div className={cn("rounded-lg p-2", tone)}>{icon}</div>
      <div className="min-w-0">
        <p className="truncate text-[10px] font-medium uppercase tracking-wide text-surface-400">
          {label}
        </p>
        <p className="text-sm font-bold text-surface-900">{value}</p>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn("badge", STATUS_CLASS[status] || "badge-neutral")}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function Progress({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-100">
      <div
        className={cn(
          "h-full rounded-full transition-all duration-500",
          clamped >= 80
            ? "bg-gradient-to-r from-emerald-500 to-teal-500"
            : clamped >= 40
            ? "bg-gradient-to-r from-brand-500 to-indigo-500"
            : "bg-gradient-to-r from-amber-400 to-orange-500"
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const MEMBER_PAGE_SIZE = 8;

export default function ChittiAnalyticsPage() {
  const initial = presetRange("30d");
  const [preset, setPreset] = useState<string>("30d");
  const [startDate, setStartDate] = useState(initial.start);
  const [endDate, setEndDate] = useState(initial.end);
  const [chittiFilter, setChittiFilter] = useState("");
  const [modeFilter, setModeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const [data, setData] = useState<ChittiOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // member table
  const [memberSearch, setMemberSearch] = useState("");
  const [memberStatus, setMemberStatus] = useState("ALL");
  const [memberSort, setMemberSort] = useState<{
    key: keyof MemberPaymentRow;
    dir: "asc" | "desc";
  }>({ key: "due_pending", dir: "desc" });
  const [memberPage, setMemberPage] = useState(1);
  const [selectedMember, setSelectedMember] = useState<MemberPaymentRow | null>(null);

  // pending section
  const [pendingBucket, setPendingBucket] = useState<string>("overdue");

  // ledger
  const [txnSearch, setTxnSearch] = useState("");
  const [showAllTxns, setShowAllTxns] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await analyticsApi.getOverview({
        start_date: startDate,
        end_date: endDate,
        chitti_id: chittiFilter || undefined,
        payment_mode: modeFilter || undefined,
        status: statusFilter || undefined,
      });
      setData(res);
      setError(null);
    } catch (e) {
      console.error(e);
      setError("Could not load the analytics dashboard.");
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, chittiFilter, modeFilter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const applyPreset = (key: string) => {
    setPreset(key);
    const range = presetRange(key);
    setStartDate(range.start);
    setEndDate(range.end);
  };

  // ---- derived tables ----
  const memberRows = useMemo(() => {
    if (!data) return [];
    let rows = data.member_rows.slice();
    const q = memberSearch.trim().toLowerCase();
    if (q) {
      rows = rows.filter(
        (r) =>
          r.member_name.toLowerCase().includes(q) ||
          (r.mobile_number || "").includes(q) ||
          (r.chitti_name || "").toLowerCase().includes(q) ||
          (r.customer_code || "").toLowerCase().includes(q)
      );
    }
    if (memberStatus !== "ALL") rows = rows.filter((r) => r.status === memberStatus);
    rows.sort((a, b) => {
      const av = a[memberSort.key];
      const bv = b[memberSort.key];
      if (typeof av === "number" && typeof bv === "number") {
        return memberSort.dir === "asc" ? av - bv : bv - av;
      }
      const as = String(av ?? "");
      const bs = String(bv ?? "");
      return memberSort.dir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return rows;
  }, [data, memberSearch, memberStatus, memberSort]);

  const memberPageCount = Math.max(1, Math.ceil(memberRows.length / MEMBER_PAGE_SIZE));
  const pagedMembers = memberRows.slice(
    (memberPage - 1) * MEMBER_PAGE_SIZE,
    memberPage * MEMBER_PAGE_SIZE
  );

  useEffect(() => {
    setMemberPage(1);
  }, [memberSearch, memberStatus, data]);

  const pendingRows = useMemo(() => {
    if (!data) return [];
    const rows = data.pending_details;
    const today = data.today.date;
    // Server business date (IST) — shift it without involving the local timezone.
    const tomorrowIso = shiftIso(today, 1);
    const weekIso = shiftIso(today, 7);
    const monthIso = shiftIso(today, 30);

    switch (pendingBucket) {
      case "today":
        return rows.filter((r) => r.due_date === today && r.days_overdue === 0);
      case "tomorrow":
        return rows.filter((r) => r.due_date === tomorrowIso);
      case "overdue":
        return rows.filter((r) => r.days_overdue > 0);
      case "week":
        return rows.filter((r) => !!r.due_date && r.due_date <= weekIso);
      case "month":
        return rows.filter((r) => !!r.due_date && r.due_date <= monthIso);
      default:
        return rows;
    }
  }, [data, pendingBucket]);

  const ledgerRows = useMemo(() => {
    if (!data) return [];
    const q = txnSearch.trim().toLowerCase();
    if (!q) return data.transactions;
    return data.transactions.filter(
      (t) =>
        t.member_name.toLowerCase().includes(q) ||
        t.chitti_name.toLowerCase().includes(q) ||
        (t.reference_number || "").toLowerCase().includes(q) ||
        t.transaction_id.toLowerCase().includes(q) ||
        (t.received_by || "").toLowerCase().includes(q)
    );
  }, [data, txnSearch]);

  const memberHistory = useMemo(() => {
    if (!data || !selectedMember) return [];
    return data.transactions.filter((t) => t.member_id === selectedMember.member_id);
  }, [data, selectedMember]);

  const sortBy = (key: keyof MemberPaymentRow) => {
    setMemberSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "desc" }
    );
  };

  const openMember = (memberId: string) => {
    const row = data?.member_rows.find((m) => m.member_id === memberId);
    if (row) setSelectedMember(row);
  };

  const today = data?.today;

  return (
    <DashboardLayout>
      <div className="space-y-7">
        {/* ============================ Header ============================ */}
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="rounded-lg bg-brand-50 p-1.5 text-brand-600">
                <TrendingUp size={16} />
              </span>
              <h1 className="text-xl font-bold tracking-tight text-surface-900 sm:text-2xl">
                Chitti Analytics
              </h1>
            </div>
            <p className="mt-1 text-sm text-surface-500">
              Complete financial control centre — every rupee collected, pending and overdue.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={load} className="btn-secondary btn-sm flex-1 sm:flex-none" disabled={loading}>
              <RefreshCw size={14} className={cn(loading && "animate-spin")} />
              Refresh
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm flex-1 sm:flex-none"
              onClick={() =>
                data &&
                exportCsv(
                  "chitti-transactions.csv",
                  [
                    "Transaction ID",
                    "Member",
                    "Chitti",
                    "Amount",
                    "Date",
                    "Mode",
                    "Reference",
                    "Received By",
                    "Status",
                  ],
                  data.transactions.map((t) => [
                    t.transaction_id,
                    t.member_name,
                    t.chitti_name,
                    t.amount,
                    t.created_at,
                    t.payment_method,
                    t.reference_number,
                    t.received_by,
                    t.status,
                  ])
                )
              }
              disabled={!data}
            >
              <Download size={14} />
              Export
            </button>
          </div>
        </div>

        {/* ============================ Filters ============================ */}
        <div className="card space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => applyPreset(p.key)}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
                  preset === p.key
                    ? "bg-brand-600 text-white shadow-sm"
                    : "bg-surface-100 text-surface-600 hover:bg-surface-200"
                )}
              >
                {p.label}
              </button>
            ))}
            <span className="ml-auto text-[11px] font-medium text-surface-400">
              Showing {data?.filters.start_date ?? startDate} → {data?.filters.end_date ?? endDate}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <label className="input-label text-xs">From</label>
              <input
                type="date"
                className="input-field py-2"
                value={startDate}
                onChange={(e) => {
                  setPreset("custom");
                  setStartDate(e.target.value);
                }}
              />
            </div>
            <div>
              <label className="input-label text-xs">To</label>
              <input
                type="date"
                className="input-field py-2"
                value={endDate}
                onChange={(e) => {
                  setPreset("custom");
                  setEndDate(e.target.value);
                }}
              />
            </div>
            <div>
              <label className="input-label text-xs">Chitti</label>
              <select
                className="input-field py-2"
                value={chittiFilter}
                onChange={(e) => setChittiFilter(e.target.value)}
              >
                <option value="">All chittis</option>
                {data?.chitti_metrics.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="input-label text-xs">Payment mode</label>
              <select
                className="input-field py-2"
                value={modeFilter}
                onChange={(e) => setModeFilter(e.target.value)}
              >
                <option value="">All modes</option>
                {Object.entries(METHOD_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="input-label text-xs">Member status</label>
              <select
                className="input-field py-2"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All statuses</option>
                <option value="PAID">Paid</option>
                <option value="PARTIALLY_PAID">Partially paid</option>
                <option value="PENDING">Pending</option>
                <option value="OVERDUE">Overdue</option>
                <option value="ADVANCE_PAID">Advance paid</option>
              </select>
            </div>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
            {error}
          </div>
        )}

        {loading && !data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : !data || data.kpis.total_chittis === 0 ? (
          <EmptyState
            icon="📊"
            title="No chitti data yet"
            description="Create a chitti with members and start recording contributions to see live analytics."
            action={
              <Link href="/chitti/new" className="btn-primary">
                <Handshake size={16} />
                Create Chitti
              </Link>
            }
          />
        ) : (
          <>
            {/* ============================ KPIs ============================ */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              <KpiCard
                label="Total Chittis"
                value={String(data.kpis.total_chittis)}
                icon={<Handshake size={18} />}
                gradient="from-brand-500 via-brand-600 to-indigo-600"
                sub={`${data.kpis.active_chittis} running · ${data.kpis.completed_chittis} completed`}
              />
              <KpiCard
                label="Total Chitti Value"
                value={formatCurrency(data.kpis.total_chitti_value)}
                icon={<IndianRupee size={18} />}
                gradient="from-violet-500 via-purple-600 to-fuchsia-600"
                sub={`${data.kpis.total_members} active members`}
              />
              <KpiCard
                label="Total Collected"
                value={formatCurrency(data.kpis.total_collected)}
                icon={<CircleDollarSign size={18} />}
                gradient="from-emerald-500 via-emerald-600 to-teal-600"
                sub={
                  <span className="flex items-center gap-1">
                    <TrendingUp size={12} />
                    {data.kpis.collection_efficiency}% of expected collected
                  </span>
                }
              />
              <KpiCard
                label="Total Pending"
                value={formatCurrency(data.kpis.total_pending)}
                icon={<Clock size={18} />}
                gradient="from-amber-500 via-orange-500 to-orange-600"
                sub={`${formatCurrency(data.kpis.total_overdue)} overdue`}
              />
              <KpiCard
                label="Collected Today"
                value={formatCurrency(data.kpis.today_collected)}
                icon={<CheckCircle2 size={18} />}
                gradient="from-sky-500 via-blue-600 to-indigo-600"
                sub={`${today?.payments_count ?? 0} payments · ${today?.members_paid ?? 0} members`}
              />
              <KpiCard
                label="Expected Today"
                value={formatCurrency(data.kpis.today_expected)}
                icon={<CalendarDays size={18} />}
                gradient="from-slate-600 via-surface-700 to-surface-800"
                sub={`${today?.members_due ?? 0} members due · ${today?.members_unpaid ?? 0} unpaid`}
              />
              <KpiCard
                label="Pending Today"
                value={formatCurrency(data.kpis.today_pending)}
                icon={<Clock size={18} />}
                gradient="from-rose-500 via-rose-600 to-red-600"
                sub={`${today?.partial_count ?? 0} partial · ${today?.overdue_count ?? 0} overdue installments`}
              />
              <KpiCard
                label="Overdue Amount"
                value={formatCurrency(data.kpis.overdue_amount)}
                icon={<AlertTriangle size={18} />}
                gradient="from-red-600 via-rose-600 to-pink-600"
                sub={`${data.kpis.overdue_members} members overdue`}
              />
              <KpiCard
                label="Collection Efficiency"
                value={`${data.kpis.collection_efficiency}%`}
                icon={<Percent size={18} />}
                gradient="from-teal-500 via-cyan-600 to-sky-600"
                sub={`${formatCurrency(data.kpis.total_collected)} of ${formatCurrency(
                  data.kpis.total_expected
                )}`}
              />
            </div>

            {/* ============================ Today ============================ */}
            <div className="card space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-surface-900">Daily Collections</h2>
                  <p className="text-xs text-surface-500">
                    Today · {today?.date} · expected vs actually received
                  </p>
                </div>
                <span className="badge-brand">
                  <CircleDollarSign size={12} />
                  {formatCurrency(today?.collected ?? 0)} today
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
                <MiniStat
                  label="Expected"
                  value={formatCurrency(today?.expected ?? 0)}
                  icon={<CalendarDays size={15} />}
                  tone="bg-brand-50 text-brand-600"
                />
                <MiniStat
                  label="Collected"
                  value={formatCurrency(today?.collected ?? 0)}
                  icon={<CheckCircle2 size={15} />}
                  tone="bg-success-50 text-success-600"
                />
                <MiniStat
                  label="Pending"
                  value={formatCurrency(today?.pending ?? 0)}
                  icon={<Clock size={15} />}
                  tone="bg-warning-50 text-warning-600"
                />
                <MiniStat
                  label="Paid today"
                  value={`${today?.members_paid ?? 0}`}
                  icon={<Users size={15} />}
                  tone="bg-emerald-50 text-emerald-600"
                />
                <MiniStat
                  label="Not paid"
                  value={`${today?.members_unpaid ?? 0}`}
                  icon={<TrendingDown size={15} />}
                  tone="bg-danger-50 text-danger-600"
                />
                <MiniStat
                  label="Overdue"
                  value={`${today?.overdue_count ?? 0}`}
                  icon={<AlertTriangle size={15} />}
                  tone="bg-rose-50 text-rose-600"
                />
                <MiniStat
                  label="Partial"
                  value={`${today?.partial_count ?? 0}`}
                  icon={<ActivityPulse />}
                  tone="bg-indigo-50 text-indigo-600"
                />
                <MiniStat
                  label="Payments"
                  value={`${today?.payments_count ?? 0}`}
                  icon={<CreditCard size={15} />}
                  tone="bg-sky-50 text-sky-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {(today?.by_method ?? []).map((m) => (
                  <div
                    key={m.mode}
                    className="flex items-center gap-3 rounded-xl border border-surface-100 bg-surface-50/50 p-3"
                  >
                    <div className="rounded-lg bg-white p-2 text-surface-600 shadow-sm">
                      {METHOD_ICON[m.mode] ?? <CreditCard size={15} />}
                    </div>
                    <div>
                      <p className="text-[10px] font-medium uppercase tracking-wide text-surface-400">
                        {METHOD_LABEL[m.mode] ?? m.mode}
                      </p>
                      <p className="text-sm font-bold text-surface-900">{formatCurrency(m.amount)}</p>
                    </div>
                  </div>
                ))}
              </div>

              <LineChart
                data={data.daily.series}
                series={[
                  { key: "expected", label: "Expected", color: "#94a3b8", dashed: true },
                  { key: "collected", label: "Collected", color: "#4f46e5", fill: true },
                ]}
                height={260}
                xLabel={(row) => String(row.date).slice(5)}
              />
            </div>

            {/* ============================ Charts ============================ */}
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <div className="card">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-surface-900">Monthly Trend</h3>
                  <span className="text-[11px] text-surface-400">Last 6 months</span>
                </div>
                <GroupedBarChart
                  data={data.monthly.series}
                  series={[
                    { key: "expected", label: "Expected", color: "#c7d2fe" },
                    { key: "collected", label: "Collected", color: "#4f46e5" },
                  ]}
                  height={230}
                  xLabel={(row) => String(row.label)}
                />
              </div>

              <div className="card">
                <h3 className="mb-4 text-sm font-semibold text-surface-900">
                  Installment Status Distribution
                </h3>
                <DonutChart
                  data={data.status_distribution.map((s) => ({
                    label: s.status.replace(/_/g, " "),
                    value: s.count,
                    color:
                      s.status === "PAID"
                        ? "#22c55e"
                        : s.status === "PARTIALLY_PAID"
                        ? "#6366f1"
                        : s.status === "OVERDUE"
                        ? "#ef4444"
                        : s.status === "ADVANCE_PAID"
                        ? "#8b5cf6"
                        : "#f59e0b",
                  }))}
                  centerLabel="Installments"
                  formatter={(v) => String(Math.round(v))}
                />
              </div>

              <div className="card">
                <h3 className="mb-4 text-sm font-semibold text-surface-900">
                  Payment Mode (range)
                </h3>
                <DonutChart
                  data={data.mode_distribution.map((m) => ({
                    label: METHOD_LABEL[m.mode] ?? m.mode,
                    value: m.amount,
                    color:
                      m.mode === "CASH"
                        ? "#16a34a"
                        : m.mode === "UPI"
                        ? "#4f46e5"
                        : m.mode === "BANK_TRANSFER"
                        ? "#0ea5e9"
                        : "#94a3b8",
                  }))}
                  centerLabel="Received"
                />
              </div>

              <div className="card">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-surface-900">Range Comparison</h3>
                  <span
                    className={cn(
                      "badge",
                      data.kpis.comparison.change_amount >= 0
                        ? "badge-success"
                        : "badge-danger"
                    )}
                  >
                    {data.kpis.comparison.change_amount >= 0 ? (
                      <TrendingUp size={12} />
                    ) : (
                      <TrendingDown size={12} />
                    )}
                    {data.kpis.comparison.previous_collected > 0
                      ? `${Math.abs(data.kpis.comparison.change_pct)}% vs previous period`
                      : "No prior-period collections"}
                  </span>
                </div>
                <div className="space-y-4">
                  {[
                    {
                      label: "Collected this range",
                      value: data.kpis.range_collected,
                      color: "bg-brand-500",
                      max: Math.max(data.kpis.range_expected, data.kpis.range_collected, 1),
                    },
                    {
                      label: "Expected this range",
                      value: data.kpis.range_expected,
                      color: "bg-surface-300",
                      max: Math.max(data.kpis.range_expected, data.kpis.range_collected, 1),
                    },
                    {
                      label: "Still pending",
                      value: data.kpis.range_pending,
                      color: "bg-warning-500",
                      max: Math.max(data.kpis.range_expected, data.kpis.range_collected, 1),
                    },
                  ].map((row) => (
                    <div key={row.label} className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-surface-500">{row.label}</span>
                        <span className="font-bold text-surface-900">
                          {formatCurrency(row.value)}
                        </span>
                      </div>
                      <div className="h-2.5 w-full overflow-hidden rounded-full bg-surface-100">
                        <div
                          className={cn("h-full rounded-full", row.color)}
                          style={{ width: `${Math.min((row.value / row.max) * 100, 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 rounded-xl bg-surface-50 p-3 text-xs text-surface-500">
                  Previous period collected{" "}
                  <span className="font-semibold text-surface-900">
                    {formatCurrency(data.kpis.comparison.previous_collected)}
                  </span>
                  . Pending amounts are never counted as revenue.
                </div>
              </div>
            </div>

            {/* ============================ Chitti-wise ============================ */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-semibold text-surface-900">Chitti-wise Financials</h2>
                  <p className="text-xs text-surface-500">
                    Collection progress for every chitti from actual schedules
                  </p>
                </div>
                <Link href="/chitti/all" className="text-xs font-semibold text-brand-600 hover:text-brand-700">
                  View all chittis →
                </Link>
              </div>

              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {data.chitti_metrics.map((c) => (
                  <div key={c.id} className="card space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-surface-900">{c.name}</p>
                        <p className="text-[11px] text-surface-400">
                          {c.chitti_code} · {c.member_count} members · period {c.current_period}/
                          {c.total_periods}
                        </p>
                      </div>
                      <span
                        className={cn(
                          "badge flex-shrink-0",
                          c.status === "RUNNING"
                            ? "badge-brand"
                            : c.status === "COMPLETED"
                            ? "badge-success"
                            : c.status === "DRAFT"
                            ? "badge-warning"
                            : "badge-neutral"
                        )}
                      >
                        {c.status}
                      </span>
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-surface-500">
                          Collected {formatCurrency(c.collected)} of {formatCurrency(c.expected)}
                        </span>
                        <span className="font-bold text-surface-900">{c.collection_pct}%</span>
                      </div>
                      <Progress pct={c.collection_pct} />
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                      <div className="rounded-lg bg-surface-50 p-2">
                        <p className="text-[10px] uppercase text-surface-400">Value</p>
                        <p className="font-bold text-surface-900">{formatCurrency(c.total_value)}</p>
                      </div>
                      <div className="rounded-lg bg-emerald-50 p-2">
                        <p className="text-[10px] uppercase text-emerald-600">Today</p>
                        <p className="font-bold text-emerald-700">{formatCurrency(c.today_collection)}</p>
                      </div>
                      <div className="rounded-lg bg-brand-50 p-2">
                        <p className="text-[10px] uppercase text-brand-600">This month</p>
                        <p className="font-bold text-brand-700">{formatCurrency(c.month_collection)}</p>
                      </div>
                      <div className="rounded-lg bg-danger-50 p-2">
                        <p className="text-[10px] uppercase text-danger-600">Overdue</p>
                        <p className="font-bold text-danger-700">{formatCurrency(c.overdue)}</p>
                      </div>
                    </div>

                    <div className="flex items-center justify-between border-t border-surface-100 pt-3">
                      <p className="text-[11px] text-surface-400">
                        Next due{" "}
                        <span className="font-semibold text-surface-700">
                          {c.next_due_date ?? "—"}
                        </span>
                      </p>
                      <Link
                        href={`/chitti/${c.id}`}
                        className="flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700"
                      >
                        Open <ArrowRight size={13} />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ============================ Member-wise ============================ */}
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-surface-900">
                    Member-wise Payment Tracking
                  </h2>
                  <p className="text-xs text-surface-500">
                    {memberRows.length} members · click a row for full payment history
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative">
                    <Search
                      size={14}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
                    />
                    <input
                      className="input-field py-2 pl-9 pr-3 text-xs"
                      placeholder="Search member, mobile, chitti…"
                      value={memberSearch}
                      onChange={(e) => setMemberSearch(e.target.value)}
                    />
                  </div>
                  <select
                    className="input-field w-auto py-2 text-xs"
                    value={memberStatus}
                    onChange={(e) => setMemberStatus(e.target.value)}
                  >
                    <option value="ALL">All statuses</option>
                    <option value="PAID">Paid</option>
                    <option value="PARTIALLY_PAID">Partially paid</option>
                    <option value="PENDING">Pending</option>
                    <option value="OVERDUE">Overdue</option>
                    <option value="ADVANCE_PAID">Advance paid</option>
                  </select>
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    onClick={() =>
                      exportCsv(
                        "chitti-members.csv",
                        [
                          "Member",
                          "Mobile",
                          "Chitti",
                          "Due",
                          "Paid",
                          "Pending",
                          "Status",
                          "Last payment",
                          "Mode",
                        ],
                        memberRows.map((r) => [
                          r.member_name,
                          r.mobile_number,
                          r.chitti_name,
                          r.expected_total,
                          r.paid_total,
                          r.pending_total,
                          r.status,
                          r.payment_date,
                          r.payment_mode,
                        ])
                      )
                    }
                  >
                    <Download size={13} />
                    CSV
                  </button>
                </div>
              </div>

              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      {[
                        ["member_name", "Member"],
                        ["chitti_name", "Chitti"],
                        ["expected_total", "Due"],
                        ["paid_total", "Paid"],
                        ["pending_total", "Pending"],
                        ["payment_date", "Last Payment"],
                        ["status", "Status"],
                      ].map(([key, label]) => (
                        <th key={key}>
                          <button
                            type="button"
                            onClick={() => sortBy(key as keyof MemberPaymentRow)}
                            className="flex items-center gap-1 uppercase tracking-wider hover:text-surface-700"
                          >
                            {label}
                            {memberSort.key === key && (
                              <span className="text-brand-500">
                                {memberSort.dir === "asc" ? "↑" : "↓"}
                              </span>
                            )}
                          </button>
                        </th>
                      ))}
                      <th className="text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedMembers.map((m) => (
                      <tr key={m.member_id} className="cursor-pointer" onClick={() => setSelectedMember(m)}>
                        <td>
                          <div className="flex items-center gap-3">
                            <span className="avatar-sm flex-shrink-0">
                              {m.member_name.slice(0, 1).toUpperCase()}
                            </span>
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-surface-900">
                                {m.member_name}
                              </p>
                              <p className="text-[11px] text-surface-400">
                                {m.mobile_number || m.customer_code || "—"}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="text-xs text-surface-600">{m.chitti_name || "—"}</td>
                        <td className="text-sm font-medium text-surface-700">
                          {formatCurrency(m.due_total)}
                        </td>
                        <td className="text-sm font-semibold text-success-600">
                          {formatCurrency(m.paid_total)}
                        </td>
                        <td
                          className={cn(
                            "text-sm font-semibold",
                            m.due_pending > 0 ? "text-warning-600" : "text-surface-400"
                          )}
                        >
                          {formatCurrency(m.due_pending)}
                        </td>
                        <td className="text-xs text-surface-500">
                          {m.payment_date ?? "—"}
                          {m.payment_mode && (
                            <span className="block text-[10px] text-surface-400">
                              {METHOD_LABEL[m.payment_mode] ?? m.payment_mode}
                            </span>
                          )}
                        </td>
                        <td>
                          <StatusBadge status={m.status} />
                        </td>
                        <td className="text-right">
                          <button
                            type="button"
                            className="btn-ghost btn-sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedMember(m);
                            }}
                          >
                            <Eye size={13} />
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                    {pagedMembers.length === 0 && (
                      <tr>
                        <td colSpan={8} className="py-10 text-center text-sm text-surface-400">
                          No members match these filters.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-surface-500">
                  Page {memberPage} of {memberPageCount}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    disabled={memberPage <= 1}
                    onClick={() => setMemberPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft size={14} />
                    Prev
                  </button>
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    disabled={memberPage >= memberPageCount}
                    onClick={() => setMemberPage((p) => Math.min(memberPageCount, p + 1))}
                  >
                    Next
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            </div>

            {/* ============================ Pending & Overdue ============================ */}
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-surface-900">Pending &amp; Overdue</h2>
                  <p className="text-xs text-surface-500">
                    {formatCurrency(
                      pendingRows.reduce((sum, r) => sum + r.amount_pending, 0)
                    )}{" "}
                    outstanding across {pendingRows.length} installment
                    {pendingRows.length !== 1 ? "s" : ""} in this filter
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {[
                    { key: "overdue", label: "Overdue" },
                    { key: "today", label: "Due today" },
                    { key: "tomorrow", label: "Due tomorrow" },
                    { key: "week", label: "This week" },
                    { key: "month", label: "This month" },
                    { key: "all", label: "All" },
                  ].map((b) => (
                    <button
                      key={b.key}
                      type="button"
                      onClick={() => setPendingBucket(b.key)}
                      className={cn(
                        "rounded-lg px-2.5 py-1.5 text-[11px] font-semibold transition-all",
                        pendingBucket === b.key
                          ? "bg-danger-600 text-white shadow-sm"
                          : "bg-surface-100 text-surface-600 hover:bg-surface-200"
                      )}
                    >
                      {b.label}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    onClick={() =>
                      exportCsv(
                        "chitti-pending.csv",
                        [
                          "Member",
                          "Mobile",
                          "Chitti",
                          "Installment",
                          "Due date",
                          "Days overdue",
                          "Pending",
                          "Last payment",
                          "Status",
                        ],
                        pendingRows.map((r) => [
                          r.member_name,
                          r.mobile_number,
                          r.chitti_name,
                          r.period_number,
                          r.due_date,
                          r.days_overdue,
                          r.amount_pending,
                          r.last_payment_date,
                          r.status,
                        ])
                      )
                    }
                  >
                    <Download size={13} />
                    CSV
                  </button>
                </div>
              </div>

              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Member</th>
                      <th>Chitti</th>
                      <th>Installment</th>
                      <th>Due date</th>
                      <th>Overdue</th>
                      <th>Pending</th>
                      <th>Outstanding</th>
                      <th className="text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingRows.slice(0, 50).map((r) => (
                      <tr
                        key={`${r.member_id}-${r.period_number}-${r.chitti_id}`}
                        className={cn(r.days_overdue > 0 && "bg-danger-50/40")}
                      >
                        <td>
                          <p className="text-sm font-semibold text-surface-900">{r.member_name}</p>
                          <p className="text-[11px] text-surface-400">{r.mobile_number || "—"}</p>
                        </td>
                        <td className="text-xs text-surface-600">{r.chitti_name}</td>
                        <td className="text-xs text-surface-600">Period {r.period_number}</td>
                        <td className="text-xs text-surface-600">{r.due_date ?? "—"}</td>
                        <td>
                          {r.days_overdue > 0 ? (
                            <span className="badge-danger">{r.days_overdue}d</span>
                          ) : (
                            <span className="badge-neutral">—</span>
                          )}
                        </td>
                        <td className="text-sm font-bold text-warning-600">
                          {formatCurrency(r.amount_pending)}
                        </td>
                        <td className="text-xs text-surface-500">
                          {formatCurrency(r.total_outstanding)}
                        </td>
                        <td>
                          <div className="flex items-center justify-end gap-1">
                            <button
                              type="button"
                              className="btn-ghost btn-sm"
                              onClick={() => openMember(r.member_id)}
                            >
                              <Eye size={13} />
                              View
                            </button>
                            <Link href="/payments/collect" className="btn-ghost btn-sm text-brand-600">
                              Collect
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {pendingRows.length === 0 && (
                      <tr>
                        <td colSpan={8} className="py-10 text-center text-sm text-surface-400">
                          Nothing pending for this filter. 🎉
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* ============================ Transactions ============================ */}
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-surface-900">Transaction Ledger</h2>
                  <p className="text-xs text-surface-500">
                    Immutable record of every chitti contribution
                  </p>
                </div>
                <div className="relative">
                  <Search
                    size={14}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
                  />
                  <input
                    className="input-field py-2 pl-9 pr-3 text-xs"
                    placeholder="Search transaction, member, reference…"
                    value={txnSearch}
                    onChange={(e) => setTxnSearch(e.target.value)}
                  />
                </div>
              </div>

              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Transaction</th>
                      <th>Member</th>
                      <th>Chitti</th>
                      <th>Amount</th>
                      <th>Date &amp; time</th>
                      <th>Mode</th>
                      <th>Reference</th>
                      <th>Received by</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(showAllTxns ? ledgerRows : ledgerRows.slice(0, 10)).map((t) => (
                      <tr key={t.id}>
                        <td className="font-mono text-[11px] text-surface-500">
                          {t.transaction_id}
                        </td>
                        <td className="text-sm font-medium text-surface-900">{t.member_name}</td>
                        <td className="text-xs text-surface-600">{t.chitti_name}</td>
                        <td
                          className={cn(
                            "text-sm font-bold",
                            t.transaction_type === "REVERSAL"
                              ? "text-danger-600"
                              : "text-success-600"
                          )}
                        >
                          {t.transaction_type === "REVERSAL" ? "−" : ""}
                          {formatCurrency(t.amount)}
                        </td>
                        <td className="text-xs text-surface-500">{t.payment_date ?? t.created_at}</td>
                        <td className="text-xs text-surface-600">
                          {t.payment_method ? METHOD_LABEL[t.payment_method] ?? t.payment_method : "—"}
                        </td>
                        <td className="text-[11px] text-surface-400">{t.reference_number || "—"}</td>
                        <td className="text-xs text-surface-600">{t.received_by || "—"}</td>
                        <td>
                          <span
                            className={cn(
                              "badge",
                              t.status === "REVERSED" ? "badge-danger" : "badge-success"
                            )}
                          >
                            {t.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {ledgerRows.length === 0 && (
                      <tr>
                        <td colSpan={9} className="py-10 text-center text-sm text-surface-400">
                          No transactions in this range.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {ledgerRows.length > 10 && (
                <div className="text-center">
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    onClick={() => setShowAllTxns((v) => !v)}
                  >
                    {showAllTxns ? "Show less" : `Show all ${ledgerRows.length} transactions`}
                  </button>
                </div>
              )}
            </div>

            {/* ============================ Financial summary ============================ */}
            <div className="card">
              <div className="mb-4 flex items-center gap-2">
                <div className="rounded-lg bg-brand-50 p-2 text-brand-600">
                  <Wallet size={16} />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-surface-900">Financial Summary</h2>
                  <p className="text-xs text-surface-500">
                    Actual money received is kept separate from scheduled / expected amounts
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                {[
                  {
                    label: "Total Receivable",
                    value: data.financial_summary.total_receivable,
                    tone: "bg-surface-50 text-surface-900",
                  },
                  {
                    label: "Total Received",
                    value: data.financial_summary.total_received,
                    tone: "bg-success-50 text-success-700",
                  },
                  {
                    label: "Total Outstanding",
                    value: data.financial_summary.total_outstanding,
                    tone: "bg-warning-50 text-warning-700",
                  },
                  {
                    label: "Total Overdue",
                    value: data.financial_summary.total_overdue,
                    tone: "bg-danger-50 text-danger-700",
                  },
                  {
                    label: "Advance Payments",
                    value: data.financial_summary.total_advance,
                    tone: "bg-brand-50 text-brand-700",
                  },
                  {
                    label: "Refunds / Reversals",
                    value: data.financial_summary.total_refunds,
                    tone: "bg-rose-50 text-rose-700",
                  },
                  {
                    label: "Daily Collection",
                    value: data.financial_summary.daily_collection,
                    tone: "bg-sky-50 text-sky-700",
                  },
                  {
                    label: "Monthly Collection",
                    value: data.financial_summary.monthly_collection,
                    tone: "bg-indigo-50 text-indigo-700",
                  },
                  {
                    label: "Yearly Collection",
                    value: data.financial_summary.yearly_collection,
                    tone: "bg-emerald-50 text-emerald-700",
                  },
                  {
                    label: "Collection Efficiency",
                    value: data.kpis.collection_efficiency,
                    tone: "bg-teal-50 text-teal-700",
                    percent: true,
                  },
                ].map((item: { label: string; value: number; tone: string; percent?: boolean }) => (
                  <div key={item.label} className={cn("rounded-xl p-3", item.tone)}>
                    <p className="text-[10px] font-semibold uppercase tracking-wide opacity-70">
                      {item.label}
                    </p>
                    <p className="mt-1 text-sm font-bold">
                      {item.percent ? `${item.value}%` : formatCurrency(item.value)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {/* ============================ Member modal ============================ */}
      {selectedMember && (
        <div className="modal-backdrop" onClick={() => setSelectedMember(null)}>
          <div
            className="modal-content max-h-[85vh] max-w-2xl overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between border-b border-surface-100 p-5">
              <div className="flex items-center gap-3">
                <span className="avatar-md">
                  {selectedMember.member_name.slice(0, 1).toUpperCase()}
                </span>
                <div>
                  <p className="text-base font-bold text-surface-900">
                    {selectedMember.member_name}
                  </p>
                  <p className="text-xs text-surface-400">
                    {selectedMember.chitti_name} · Member #{selectedMember.member_number}
                    {selectedMember.mobile_number ? ` · ${selectedMember.mobile_number}` : ""}
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="btn-ghost btn-sm"
                onClick={() => setSelectedMember(null)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-5 p-5">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-xl bg-surface-50 p-3">
                  <p className="text-[10px] uppercase text-surface-400">Due to date</p>
                  <p className="text-sm font-bold text-surface-900">
                    {formatCurrency(selectedMember.due_total)}
                  </p>
                </div>
                <div className="rounded-xl bg-success-50 p-3">
                  <p className="text-[10px] uppercase text-success-600">Paid</p>
                  <p className="text-sm font-bold text-success-700">
                    {formatCurrency(selectedMember.paid_total)}
                  </p>
                </div>
                <div className="rounded-xl bg-warning-50 p-3">
                  <p className="text-[10px] uppercase text-warning-600">Pending</p>
                  <p className="text-sm font-bold text-warning-700">
                    {formatCurrency(selectedMember.due_pending)}
                  </p>
                </div>
                <div className="rounded-xl bg-danger-50 p-3">
                  <p className="text-[10px] uppercase text-danger-600">Overdue</p>
                  <p className="text-sm font-bold text-danger-700">
                    {formatCurrency(selectedMember.overdue_amount)}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface-50 px-3 py-2 text-[11px] text-surface-500">
                <span>
                  Total commitment{" "}
                  <span className="font-semibold text-surface-900">
                    {formatCurrency(selectedMember.expected_total)}
                  </span>
                </span>
                <span>
                  Total outstanding{" "}
                  <span className="font-semibold text-surface-900">
                    {formatCurrency(selectedMember.pending_total)}
                  </span>
                </span>
                {selectedMember.advance_amount > 0 && (
                  <span>
                    Advance{" "}
                    <span className="font-semibold text-brand-700">
                      {formatCurrency(selectedMember.advance_amount)}
                    </span>
                  </span>
                )}
              </div>

              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-surface-900">Payment History</h3>
                <StatusBadge status={selectedMember.status} />
              </div>

              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Transaction</th>
                      <th>Date</th>
                      <th>Mode</th>
                      <th>Amount</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {memberHistory.map((t) => (
                      <tr key={t.id}>
                        <td className="font-mono text-[11px] text-surface-500">
                          {t.transaction_id}
                        </td>
                        <td className="text-xs text-surface-600">{t.payment_date ?? t.created_at}</td>
                        <td className="text-xs text-surface-600">
                          {t.payment_method ? METHOD_LABEL[t.payment_method] ?? t.payment_method : "—"}
                        </td>
                        <td className="text-sm font-bold text-success-600">
                          {formatCurrency(t.amount)}
                        </td>
                        <td>
                          <span className="badge-success">{t.status}</span>
                        </td>
                      </tr>
                    ))}
                    {memberHistory.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-sm text-surface-400">
                          No payments recorded for this member yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-end gap-2">
                <Link href="/payments/collect" className="btn-primary btn-sm">
                  <CircleDollarSign size={14} />
                  Collect payment
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}

function ActivityPulse() {
  return <Percent size={15} />;
}
