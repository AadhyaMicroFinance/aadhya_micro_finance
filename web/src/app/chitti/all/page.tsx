"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { chittiApi, type ChittiInstance } from "@/services/chitti";
import { formatCurrency, formatDate, cn, getStatusColor } from "@/lib/utils";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { Plus, LinkIcon } from "lucide-react";

export default function AllChittisPage() {
  const [chittis, setChittis] = useState<ChittiInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try { const res = await chittiApi.listChittis({ per_page: 50, status: statusFilter || undefined }); setChittis(res.data); }
      catch (e) { console.error(e); }
      finally { setLoading(false); }
    };
    load();
  }, [statusFilter]);

  const filters = [
    { value: "", label: "All" },
    { value: "DRAFT", label: "Draft" },
    { value: "RUNNING", label: "Running" },
    { value: "PAUSED", label: "Paused" },
    { value: "COMPLETED", label: "Completed" },
    { value: "CANCELLED", label: "Cancelled" },
  ];

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">All Chittis</h1>
            <p className="mt-1 text-sm text-surface-500">Browse and manage all chittis</p>
          </div>
          <Link href="/chitti/new" className="btn-primary"><Plus size={16} /> New Chitti</Link>
        </div>

        <div className="tabs">
          {filters.map((f) => (
            <button key={f.value} onClick={() => setStatusFilter(f.value)} className={cn("tab", statusFilter === f.value && "tab-active")}>{f.label}</button>
          ))}
        </div>

        {loading ? <TableSkeleton rows={5} cols={9} /> : chittis.length === 0 ? (
          <EmptyState icon="🤝" title="No chittis found" description="Create your first chitti to get started." action={<Link href="/chitti/new" className="btn-primary"><Plus size={16} /> New Chitti</Link>} />
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr><th>Code</th><th>Name</th><th>Plan</th><th>Value</th><th>Members</th><th>Period</th><th>Start</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {chittis.map((c) => (
                  <tr key={c.id}>
                    <td className="font-mono text-xs text-surface-500">{c.chitti_code}</td>
                    <td><Link href={`/chitti/${c.id}`} className="text-sm font-semibold text-brand-600 hover:text-brand-700">{c.name}</Link></td>
                    <td className="text-sm text-surface-500">{c.plan_name || "—"}</td>
                    <td className="text-sm font-medium">{formatCurrency(c.total_value)}</td>
                    <td className="text-sm">{c.enrolled_members ?? 0} / {c.member_capacity ?? c.member_count}</td>
                    <td className="text-sm text-surface-500">{c.current_period} / {String((c.plan_snapshot as Record<string, unknown>)?.duration || "—")}</td>
                    <td className="text-sm text-surface-500">{formatDate(c.start_date)}</td>
                    <td><span className={cn("badge", getStatusColor(c.status))}>{c.status}</span></td>
                    <td><Link href={`/chitti/${c.id}`} className="text-brand-600"><LinkIcon size={14} /></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
