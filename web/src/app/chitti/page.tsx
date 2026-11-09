"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  chittiApi,
  type ChittiDashboardItem,
} from "@/services/chitti";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import { getApiErrorMessage } from "@/services/api-client";
import ProgressBar from "@/components/ui/ProgressBar";
import EmptyState from "@/components/ui/EmptyState";
import { CardSkeleton } from "@/components/ui/Skeleton";
import { Plus, Handshake, TrendingUp, TrendingDown, Users, Calendar, ArrowRight } from "lucide-react";

type StatusTab = "all" | "running" | "upcoming" | "completed";

export default function ChittiDashboardPage() {
  const [items, setItems] = useState<ChittiDashboardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<StatusTab>("all");

  useEffect(() => {
    const load = async () => {
      try {
        const data = await chittiApi.getDashboard();
        setItems(data);
      } catch (e) {
        console.error(e);
        setError(getApiErrorMessage(e, "Could not load the Chitti dashboard."));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const filtered = items.filter((item) => {
    if (activeTab === "all") return true;
    return item.status.toLowerCase() === activeTab;
  });

  const stats = {
    running: items.filter((i) => i.status === "RUNNING").length,
    totalCollected: items.reduce((s, i) => s + (i.actual_collection || 0), 0),
    totalPending: items.reduce((s, i) => s + (i.pending_collection || 0), 0),
    totalMembers: items.reduce((s, i) => s + (i.member_count || 0), 0),
  };

  return (
    <DashboardLayout>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Chittis</h1>
            <p className="mt-1 text-sm text-surface-500">Manage your chitti groups and track collections</p>
          </div>
          <Link href="/chitti/new" className="btn-primary">
            <Plus size={16} />
            Create Chitti
          </Link>
        </div>

        {error && (
          <div className="rounded-xl border border-danger-100 bg-danger-50 p-4 text-sm text-danger-700">{error}</div>
        )}

        {/* Stats */}
        {!loading && items.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="card flex items-center gap-4">
              <div className="rounded-xl bg-brand-50 p-3 text-brand-600">
                <Handshake size={20} />
              </div>
              <div>
                <p className="text-xs font-medium text-surface-500 uppercase">Running</p>
                <p className="text-xl font-bold text-surface-900">{stats.running}</p>
              </div>
            </div>
            <div className="card flex items-center gap-4">
              <div className="rounded-xl bg-success-50 p-3 text-success-600">
                <TrendingUp size={20} />
              </div>
              <div>
                <p className="text-xs font-medium text-surface-500 uppercase">Collected</p>
                <p className="text-xl font-bold text-surface-900">{formatCurrency(stats.totalCollected)}</p>
              </div>
            </div>
            <div className="card flex items-center gap-4">
              <div className="rounded-xl bg-warning-50 p-3 text-warning-600">
                <TrendingDown size={20} />
              </div>
              <div>
                <p className="text-xs font-medium text-surface-500 uppercase">Pending</p>
                <p className="text-xl font-bold text-surface-900">{formatCurrency(stats.totalPending)}</p>
              </div>
            </div>
            <div className="card flex items-center gap-4">
              <div className="rounded-xl bg-purple-50 p-3 text-purple-600">
                <Users size={20} />
              </div>
              <div>
                <p className="text-xs font-medium text-surface-500 uppercase">Total Members</p>
                <p className="text-xl font-bold text-surface-900">{stats.totalMembers}</p>
              </div>
            </div>
          </div>
        )}

        {/* Status Tabs */}
        <div className="flex items-center justify-between">
          <div className="tabs">
            {(["all", "running", "upcoming", "completed"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn("tab", activeTab === tab && "tab-active")}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>
          <p className="text-sm text-surface-500">
            {filtered.length} chitti{filtered.length !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Chitti Cards */}
        {loading ? (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon="🤝"
            title={activeTab === "all" ? "No chittis yet" : `No ${activeTab} chittis`}
            description="Create your first chitti to start managing members, collections and payouts."
            action={
              <Link href="/chitti/new" className="btn-primary">
                <Plus size={16} />
                Create Chitti
              </Link>
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {filtered.map((item) => {
              const progressPct = item.total_periods > 0
                ? Math.round((item.current_period / item.total_periods) * 100)
                : 0;

              return (
                <Link
                  key={item.id}
                  href={`/chitti/${item.id}`}
                  className="card-hover group"
                >
                  <div className="space-y-4">
                    {/* Header */}
                    <div className="flex items-start justify-between">
                      <div className="space-y-1">
                        <h3 className="text-base font-semibold text-surface-900 group-hover:text-brand-700 transition-colors">
                          {item.name}
                        </h3>
                        <p className="text-xs text-surface-400">
                          {item.plan_name || "Custom"} • {item.chitti_code}
                        </p>
                      </div>
                      <span className={cn(
                        "badge",
                        item.status === "RUNNING" ? "badge-brand" :
                        item.status === "DRAFT" ? "badge-warning" :
                        item.status === "COMPLETED" ? "badge-success" :
                        "badge-neutral"
                      )}>
                        <span className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          item.status === "RUNNING" ? "bg-brand-500" :
                          item.status === "DRAFT" ? "bg-warning-500" :
                          item.status === "COMPLETED" ? "bg-success-500" :
                          "bg-surface-400"
                        )} />
                        {item.status}
                      </span>
                    </div>

                    {/* Progress */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-surface-500">
                          Period {item.current_period} of {item.total_periods}
                        </span>
                        <span className="font-medium text-surface-700">{progressPct}%</span>
                      </div>
                      <ProgressBar value={progressPct} color={item.status === "RUNNING" ? "brand" : "success"} />
                    </div>

                    {/* Financial Summary */}
                    <div className="grid grid-cols-3 gap-3">
                      <div className="text-center">
                        <p className="text-[10px] font-medium text-surface-400 uppercase">Value</p>
                        <p className="text-sm font-bold text-surface-900">{formatCurrency(item.total_value)}</p>
                      </div>
                      <div className="text-center">
                        <p className="text-[10px] font-medium text-surface-400 uppercase">Collected</p>
                        <p className="text-sm font-bold text-success-600">{formatCurrency(item.actual_collection)}</p>
                      </div>
                      <div className="text-center">
                        <p className="text-[10px] font-medium text-surface-400 uppercase">Pending</p>
                        <p className="text-sm font-bold text-warning-600">{formatCurrency(item.pending_collection)}</p>
                      </div>
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between pt-3 border-t border-surface-100">
                      <div className="flex items-center gap-4 text-xs text-surface-500">
                        <span className="flex items-center gap-1">
                          <Users size={12} />
                          {item.member_count} / {item.member_capacity ?? item.member_count} members
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar size={12} />
                          {formatDate(item.start_date)}
                        </span>
                      </div>
                      <ArrowRight size={16} className="text-surface-300 group-hover:text-brand-500 group-hover:translate-x-1 transition-all" />
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
