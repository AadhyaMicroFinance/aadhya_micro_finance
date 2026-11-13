"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import CollectContributionModal from "@/components/chitti/CollectContributionModal";
import { chittiApi, type ChittiDashboardItem, type ChittiMember } from "@/services/chitti";
import apiClient, { getApiErrorDetails, getApiErrorMessage } from "@/services/api-client";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import ProgressBar from "@/components/ui/ProgressBar";
import EmptyState from "@/components/ui/EmptyState";
import { CardSkeleton } from "@/components/ui/Skeleton";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Handshake,
  IndianRupee,
  Plus,
  Search,
  TrendingDown,
  TrendingUp,
  Users,
  Wallet,
  X,
} from "lucide-react";

type StatusTab = "all" | "draft" | "running" | "completed";

interface PendingRow {
  member_id: string;
  member_name: string;
  mobile_number: string | null;
  chitti_id: string;
  chitti_name: string;
  period_number: number;
  due_date: string | null;
  days_overdue: number;
  amount_pending: number;
  status: string;
}

interface Overview {
  kpis: {
    total_collected: number;
    total_pending: number;
    total_overdue: number;
    active_chittis: number;
    total_members: number;
  };
  today: { collected: number; expected: number };
  pending_details: PendingRow[];
}

const money = (value: number | string | null | undefined) =>
  formatCurrency(Number(value || 0));

/** Small label used across the workspace cards. */
function Stat({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  tone: string;
}) {
  return (
    <div className="card flex flex-col gap-1 p-4 sm:flex-row sm:items-start sm:gap-4 sm:p-6">
      <div className={cn("hidden rounded-xl p-3 sm:block", tone)}>{icon}</div>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase leading-tight tracking-wide text-surface-500 sm:text-[11px]">
          {label}
        </p>
        <p className="mt-1 text-lg font-bold leading-tight text-surface-900 tabular-nums sm:text-xl">
          {value}
        </p>
        <p className="mt-0.5 text-[11px] leading-snug text-surface-500 sm:text-xs">{hint}</p>
      </div>
    </div>
  );
}

/** Picks which member to collect from, so the landing page needs no navigation. */
function MemberPickerModal({
  chitti,
  onClose,
  onPick,
}: {
  chitti: ChittiDashboardItem;
  onClose: () => void;
  onPick: (member: ChittiMember) => void;
}) {
  const [members, setMembers] = useState<ChittiMember[] | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    chittiApi
      .listMembers(chitti.id)
      .then((data) => {
        if (!cancelled) setMembers(data);
      })
      .catch((e) => {
        if (!cancelled) setError(getApiErrorMessage(e, "Could not load members."));
      });
    return () => {
      cancelled = true;
    };
  }, [chitti.id]);

  const visible = (members ?? []).filter((m) => {
    if (search.trim().length === 0) return true;
    const needle = search.toLowerCase();
    return (
      (m.customer_name ?? "").toLowerCase().includes(needle) ||
      (m.mobile_number ?? "").includes(search) ||
      (m.customer_code ?? "").toLowerCase().includes(needle)
    );
  });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-surface-100 px-4 py-4 sm:px-6">
          <div className="min-w-0">
            <h3 className="text-lg font-bold text-surface-900">Collect from a member</h3>
            <p className="text-xs text-surface-500">
              {chitti.name} • {chitti.chitti_code}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-surface-400 hover:bg-surface-100"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3 p-4 sm:p-6">
          <div className="relative">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
            />
            <input
              autoFocus
              className="input-field pl-9"
              placeholder="Search member by name or phone"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {error && (
            <p className="rounded-xl bg-danger-50 px-3 py-2 text-sm text-danger-700">{error}</p>
          )}

          {members === null ? (
            <p className="text-sm text-surface-500">Loading members…</p>
          ) : visible.length === 0 ? (
            <p className="text-sm text-surface-500">No members match that search.</p>
          ) : (
            <div className="max-h-[45dvh] space-y-2 overflow-y-auto pr-1 sm:max-h-72">
              {visible.map((m) => {
                const due = Number(m.outstanding || 0);
                return (
                  <button
                    key={m.id}
                    onClick={() => onPick(m)}
                    className="flex w-full items-center justify-between rounded-xl border border-surface-100 p-3 text-left hover:border-brand-200 hover:bg-brand-50/40 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-surface-900">
                        {m.customer_name || m.customer_code}
                      </p>
                      <p className="text-xs text-surface-500">
                        #{m.member_number} • {m.status.replace(/_/g, " ").toLowerCase()} •{" "}
                        {m.mobile_number || "no phone"}
                      </p>
                    </div>
                    <div className="ml-2 shrink-0 text-right">
                      <p className={cn("text-sm font-bold", due > 0 ? "text-warning-600" : "text-success-600")}>
                        {due > 0 ? `${money(due)} due` : "All paid"}
                      </p>
                      <p className="text-[11px] text-surface-400">
                        paid {money(m.total_paid)}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ChittiWorkspacePage() {
  const [items, setItems] = useState<ChittiDashboardItem[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string; blockers?: { code: string; message: string }[] } | null>(null);
  const [activeTab, setActiveTab] = useState<StatusTab>("all");
  const [search, setSearch] = useState("");
  const [starting, setStarting] = useState<string | null>(null);
  const [picker, setPicker] = useState<ChittiDashboardItem | null>(null);
  const [collect, setCollect] = useState<{
    chittiId: string;
    member: { id: string; name: string; number?: number | null };
    period?: number;
  } | null>(null);

  const load = useCallback(async () => {
    try {
      const [dash, ov] = await Promise.all([
        chittiApi.getDashboard(),
        apiClient
          .get<{ data: Overview }>("/analytics/chitti/overview")
          .then((r) => r.data.data)
          .catch(() => null),
      ]);
      setItems(dash);
      if (ov) setOverview(ov);
      setError(null);
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not load the Chitti workspace."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => {
    const running = items.filter((i) => i.status === "RUNNING");
    const needingAgreements = items.filter(
      (i) => (i.active_members ?? 0) < (i.enrolled_members ?? i.member_count)
    );
    return {
      running: running.length,
      members: items.reduce((sum, i) => sum + Number(i.enrolled_members ?? i.member_count ?? 0), 0),
      collected: items.reduce((sum, i) => sum + Number(i.actual_collection || 0), 0),
      pending: items.reduce((sum, i) => sum + Number(i.pending_collection || 0), 0),
      needingAgreements,
    };
  }, [items]);

  const pendingRows = useMemo(() => {
    const rows = overview?.pending_details ?? [];
    return [...rows].sort((a, b) => b.days_overdue - a.days_overdue).slice(0, 8);
  }, [overview]);

  const filtered = items.filter((item) => {
    const matchesTab =
      activeTab === "all" ? true : item.status.toLowerCase() === activeTab;
    if (!matchesTab) return false;
    if (search.trim().length === 0) return true;
    const needle = search.toLowerCase();
    return (
      item.name.toLowerCase().includes(needle) ||
      item.chitti_code.toLowerCase().includes(needle) ||
      (item.plan_name ?? "").toLowerCase().includes(needle)
    );
  });

  const startChitti = async (item: ChittiDashboardItem) => {
    if (starting) return;
    setStarting(item.id);
    setFeedback(null);
    try {
      await chittiApi.changeStatus(item.id, "start");
      await load();
      setFeedback({
        type: "success",
        message: `${item.name} is now running. Members can start contributing.`,
      });
    } catch (e: unknown) {
      const details = getApiErrorDetails<{ blockers?: { code: string; message: string }[] }>(e);
      setFeedback({
        type: "error",
        message: getApiErrorMessage(e, "This chitti cannot start yet."),
        blockers: details?.blockers,
      });
    } finally {
      setStarting(null);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-7">
        {/* Header */}
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-tight text-surface-900 sm:text-2xl">
              Chitti workspace
            </h1>
            <p className="mt-1 text-sm leading-snug text-surface-500">
              Collect, add members and start chittis from one screen.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            <Link href="/chitti/new" className="btn-primary col-span-2 order-first sm:order-last">
              <Plus size={16} /> New Chitti
            </Link>
            <Link href="/chitti/analytics" className="btn-secondary">
              Reports
            </Link>
            <Link href="/chitti/plans" className="btn-secondary">
              Chitti plans
            </Link>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-danger-100 bg-danger-50 p-4 text-sm text-danger-700">
            {error}
          </div>
        )}

        {feedback && (
          <div
            className={cn(
              "rounded-2xl border p-4 text-sm",
              feedback.type === "success"
                ? "border-success-100 bg-success-50 text-success-800"
                : "border-danger-100 bg-danger-50 text-danger-800"
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">{feedback.message}</p>
                {feedback.blockers && feedback.blockers.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {feedback.blockers.map((b) => (
                      <li key={b.code}>{b.message}</li>
                    ))}
                  </ul>
                )}
              </div>
              <button
                onClick={() => setFeedback(null)}
                className="rounded-lg p-1 hover:bg-white/60"
                aria-label="Dismiss"
              >
                <X size={16} />
              </button>
            </div>
          </div>
        )}

        {/* KPIs */}
        {loading ? (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <Stat
              label="Running chittis"
              value={String(stats.running)}
              hint={`${items.length} total • ${stats.needingAgreements.length} need agreements`}
              icon={<Handshake size={20} />}
              tone="bg-brand-50 text-brand-600"
            />
            <Stat
              label="Members enrolled"
              value={String(stats.members)}
              hint="Across all chittis (cancelled excluded)"
              icon={<Users size={20} />}
              tone="bg-purple-50 text-purple-600"
            />
            <Stat
              label="Collected"
              value={money(stats.collected)}
              hint={`Today ${money(overview?.today?.collected ?? 0)}`}
              icon={<TrendingUp size={20} />}
              tone="bg-success-50 text-success-600"
            />
            <Stat
              label="Pending"
              value={money(stats.pending)}
              hint={`${pendingRows.length} member${pendingRows.length === 1 ? "" : "s"} to follow up`}
              icon={<TrendingDown size={20} />}
              tone="bg-warning-50 text-warning-600"
            />
          </div>
        )}

        {/* Pending collections — the daily job */}
        <section id="pending" className="card">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-surface-900">
                Collect contributions
              </h2>
              <p className="mt-0.5 text-sm text-surface-500">
                Members with money outstanding, most overdue first. Collect without opening
                another screen.
              </p>
            </div>
            <Link href="/chitti/analytics" className="text-sm font-semibold text-brand-600 hover:text-brand-700">
              Open full report →
            </Link>
          </div>

          {loading ? (
            <p className="text-sm text-surface-500">Loading pending contributions…</p>
          ) : pendingRows.length === 0 ? (
            <div className="flex items-center gap-3 rounded-xl bg-success-50 p-4 text-sm text-success-700">
              <CheckCircle2 size={18} /> Nothing pending. Every member is up to date.
            </div>
          ) : (
            <>
              {/* Phones: one card per member, so nothing needs sideways scrolling. */}
              <div className="space-y-2 md:hidden">
                {pendingRows.map((row) => (
                  <div
                    key={`${row.chitti_id}-${row.member_id}-${row.period_number}`}
                    className="rounded-xl border border-surface-100 p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-surface-900">
                          {row.member_name}
                        </p>
                        <p className="text-[11px] text-surface-500">{row.mobile_number || "—"}</p>
                      </div>
                      <p className="shrink-0 text-sm font-bold text-warning-600">
                        {money(row.amount_pending)}
                      </p>
                    </div>
                    <p className="mt-1 truncate text-xs text-surface-500">
                      {row.chitti_name} • Period {row.period_number}
                    </p>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span
                        className={cn(
                          "badge text-[10px]",
                          row.days_overdue > 0
                            ? "bg-danger-50 text-danger-700"
                            : "bg-surface-100 text-surface-600"
                        )}
                      >
                        {row.due_date ? formatDate(row.due_date) : "—"}
                        {row.days_overdue > 0 ? ` • ${row.days_overdue}d late` : ""}
                      </span>
                      <button
                        className="btn-primary btn-sm"
                        onClick={() =>
                          setCollect({
                            chittiId: row.chitti_id,
                            member: { id: row.member_id, name: row.member_name },
                            period: row.period_number,
                          })
                        }
                      >
                        <IndianRupee size={14} /> Collect
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="hidden overflow-x-auto md:block">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Member</th>
                      <th>Chitti</th>
                      <th>Period</th>
                      <th>Due</th>
                      <th className="text-right">Pending</th>
                      <th className="text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingRows.map((row) => (
                      <tr key={`${row.chitti_id}-${row.member_id}-${row.period_number}`}>
                        <td>
                          <p className="font-medium text-surface-900">{row.member_name}</p>
                          <p className="text-xs text-surface-500">{row.mobile_number || "—"}</p>
                        </td>
                        <td className="text-surface-600">{row.chitti_name}</td>
                        <td className="text-surface-600">Period {row.period_number}</td>
                        <td>
                          <span
                            className={cn(
                              "badge",
                              row.days_overdue > 0
                                ? "bg-danger-50 text-danger-700"
                                : "bg-surface-100 text-surface-600"
                            )}
                          >
                            {row.due_date ? formatDate(row.due_date) : "—"}
                            {row.days_overdue > 0 ? ` • ${row.days_overdue}d late` : ""}
                          </span>
                        </td>
                        <td className="text-right font-semibold text-warning-600">
                          {money(row.amount_pending)}
                        </td>
                        <td className="text-right">
                          <button
                            className="btn-primary btn-sm"
                            onClick={() =>
                              setCollect({
                                chittiId: row.chitti_id,
                                member: { id: row.member_id, name: row.member_name },
                                period: row.period_number,
                              })
                            }
                          >
                            <IndianRupee size={14} /> Collect
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        {/* Chitti list */}
        <section className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
            <div className="tabs w-full sm:w-auto">
              {(["all", "draft", "running", "completed"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={cn("tab", activeTab === tab && "tab-active")}
                >
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>
            <div className="relative w-full sm:max-w-xs">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
              />
              <input
                className="input-field pl-9"
                placeholder="Search chitti or code"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <CardSkeleton key={i} />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon="🤝"
              title={items.length === 0 ? "No chittis yet" : "No chittis match"}
              description={
                items.length === 0
                  ? "Create your first chitti, then add members and start collecting."
                  : "Try another tab or clear the search."
              }
              action={
                items.length === 0 ? (
                  <Link href="/chitti/new" className="btn-primary">
                    <Plus size={16} /> Create Chitti
                  </Link>
                ) : undefined
              }
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {filtered.map((item) => {
                const capacity = item.member_capacity ?? item.member_count;
                const enrolled = item.enrolled_members ?? item.member_count;
                const active = item.active_members ?? 0;
                const ready = item.display_state === "READY_TO_START";
                const progressPct =
                  item.total_periods > 0
                    ? Math.round((Number(item.current_period) / Number(item.total_periods)) * 100)
                    : 0;

                return (
                  <div key={item.id} className="card space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <Link
                          href={`/chitti/${item.id}`}
                          className="text-base font-semibold text-surface-900 hover:text-brand-700"
                        >
                          {item.name}
                        </Link>
                        <p className="mt-0.5 text-xs text-surface-400">
                          {item.chitti_code} • {item.plan_name || "Custom plan"}
                        </p>
                      </div>
                      <span
                        className={cn(
                          "badge",
                          item.status === "RUNNING"
                            ? "badge-brand"
                            : item.status === "DRAFT"
                              ? "badge-warning"
                              : item.status === "COMPLETED"
                                ? "badge-success"
                                : "badge-neutral"
                        )}
                      >
                        {item.display_state
                          ? item.display_state.replace(/_/g, " ").toLowerCase()
                          : item.status}
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-1.5 rounded-xl bg-surface-50 p-2.5 text-center sm:gap-2 sm:p-3">
                      <div>
                        <p className="text-[9px] font-semibold uppercase leading-tight text-surface-400 sm:text-[10px]">
                          Members
                        </p>
                        <p className="truncate text-xs font-bold text-surface-900 sm:text-sm">
                          {enrolled}/{capacity}
                        </p>
                        <p className="text-[10px] text-surface-500">{active} signed</p>
                      </div>
                      <div>
                        <p className="text-[9px] font-semibold uppercase leading-tight text-surface-400 sm:text-[10px]">
                          Collected
                        </p>
                        <p className="truncate text-xs font-bold text-success-600 sm:text-sm">
                          {money(item.actual_collection)}
                        </p>
                        <p className="truncate text-[10px] text-surface-500">of {money(item.expected_collection)}</p>
                      </div>
                      <div>
                        <p className="text-[9px] font-semibold uppercase leading-tight text-surface-400 sm:text-[10px]">
                          Pending
                        </p>
                        <p className="truncate text-xs font-bold text-warning-600 sm:text-sm">
                          {money(item.pending_collection)}
                        </p>
                        <p className="truncate text-[10px] text-surface-500">
                          {item.next_due_date ? formatDate(item.next_due_date) : "no due"}
                        </p>
                      </div>
                    </div>

                    {item.status !== "COMPLETED" && (
                      <div className="space-y-1">
                        <div className="flex justify-between text-[11px] text-surface-500">
                          <span className="inline-flex items-center gap-1">
                            <CalendarDays size={12} /> Period {item.current_period} of{" "}
                            {item.total_periods}
                          </span>
                          <span>{progressPct}%</span>
                        </div>
                        <ProgressBar value={progressPct} color={item.status === "RUNNING" ? "brand" : "success"} />
                      </div>
                    )}

                    <div className="flex flex-wrap items-center gap-2 border-t border-surface-100 pt-3">
                      {item.status === "RUNNING" ? (
                        <button
                          className="btn-primary btn-sm flex-1 sm:flex-none"
                          onClick={() => setPicker(item)}
                        >
                          <Wallet size={14} /> Collect
                        </button>
                      ) : ready ? (
                        <button
                          className="btn-primary btn-sm flex-1 sm:flex-none"
                          onClick={() => startChitti(item)}
                          disabled={starting === item.id}
                        >
                          {starting === item.id ? "Starting…" : "Start chitti"}
                        </button>
                      ) : (
                        <Link href={`/chitti/${item.id}`} className="btn-primary btn-sm flex-1 sm:flex-none">
                          Continue setup
                        </Link>
                      )}

                      {item.status === "DRAFT" ? (
                        <Link href={`/chitti/${item.id}#members`} className="btn-secondary btn-sm flex-1 sm:flex-none">
                          <Users size={14} /> Add members
                        </Link>
                      ) : (
                        <Link href={`/chitti/${item.id}`} className="btn-secondary btn-sm flex-1 sm:flex-none">
                          <Users size={14} /> Members
                        </Link>
                      )}

                      <Link
                        href={`/chitti/${item.id}`}
                        className="ml-auto inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-surface-500 hover:text-brand-700"
                      >
                        Open <ChevronRight size={16} />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Guided next steps for a brand-new employee */}
        {!loading && items.length > 0 && (
          <section className="card">
            <h2 className="text-base font-semibold text-surface-900">How chittis work</h2>
            <p className="mt-0.5 text-sm text-surface-500">
              Follow these four steps for every new chitti. The buttons above do each one.
            </p>
            <ol className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { n: 1, t: "Create the chitti", d: "Pick a plan, name it and save. It starts as a draft." },
                { n: 2, t: "Add members", d: "Search an existing customer and enroll them until seats fill." },
                { n: 3, t: "Print & sign agreements", d: "Generate, print and mark each agreement signed." },
                { n: 4, t: "Start & collect", d: "Start the chitti, then record contributions as money comes in." },
              ].map((step) => (
                <li key={step.n} className="rounded-xl border border-surface-100 p-3">
                  <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-700">
                    {step.n}
                  </span>
                  <p className="mt-2 text-sm font-semibold text-surface-900">{step.t}</p>
                  <p className="mt-0.5 text-xs text-surface-500">{step.d}</p>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>

      {/* Modals */}
      {picker && (
        <MemberPickerModal
          chitti={picker}
          onClose={() => setPicker(null)}
          onPick={(member) => {
            setPicker(null);
            setCollect({
              chittiId: picker.id,
              member: {
                id: member.id,
                name: member.customer_name || member.customer_code || "Member",
                number: member.member_number,
              },
            });
          }}
        />
      )}

      {collect && (
        <CollectContributionModal
          chittiId={collect.chittiId}
          member={collect.member}
          presetPeriod={collect.period}
          onClose={() => setCollect(null)}
          onSaved={async (message) => {
            setCollect(null);
            await load();
            setFeedback({ type: "success", message });
          }}
        />
      )}
    </DashboardLayout>
  );
}
