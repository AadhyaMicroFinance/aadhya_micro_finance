"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { chittiApi, type ChittiPlan } from "@/services/chitti";
import { formatCurrency, cn } from "@/lib/utils";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { Plus, Copy, ToggleLeft, ToggleRight } from "lucide-react";

export default function ChittiPlansPage() {
  const [plans, setPlans] = useState<ChittiPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(false);

  const loadPlans = async () => {
    setLoading(true);
    try { const res = await chittiApi.listPlans({ per_page: 50, active_only: !showAll }); setPlans(res.data); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadPlans(); }, [showAll]);

  const handleDuplicate = async (planId: string) => {
    if (!confirm("Duplicate this plan?")) return;
    try { await chittiApi.duplicatePlan(planId); loadPlans(); } catch (e) { console.error(e); }
  };

  const handleToggleActive = async (plan: ChittiPlan) => {
    try {
      if (plan.is_active) await chittiApi.deactivatePlan(plan.id);
      else await chittiApi.activatePlan(plan.id);
      loadPlans();
    } catch (e) { console.error(e); }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Chitti Plans</h1>
            <p className="mt-1 text-sm text-surface-500">Reusable templates for creating chittis</p>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => setShowAll(!showAll)} className="btn-ghost text-sm">
              {showAll ? <ToggleRight size={16} className="text-brand-600" /> : <ToggleLeft size={16} />}
              Show inactive
            </button>
            <Link href="/chitti/plans/new" className="btn-primary"><Plus size={16} /> New Plan</Link>
          </div>
        </div>

        {loading ? <TableSkeleton rows={5} cols={8} /> : plans.length === 0 ? (
          <EmptyState icon="📋" title="No plans yet" description="Create your first plan to get started." action={<Link href="/chitti/plans/new" className="btn-primary"><Plus size={16} /> New Plan</Link>} />
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr><th>Code</th><th>Name</th><th>Type</th><th>Value</th><th>Members</th><th>Frequency</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.id}>
                    <td className="font-mono text-xs text-surface-500">{plan.plan_code}</td>
                    <td><Link href={`/chitti/plans/${plan.id}`} className="text-sm font-semibold text-brand-600 hover:text-brand-700">{plan.name}</Link></td>
                    <td><span className="badge-info">{plan.chitti_type}</span></td>
                    <td className="text-sm font-medium">{formatCurrency(plan.total_value)}</td>
                    <td className="text-sm">{plan.member_count}</td>
                    <td className="text-sm text-surface-500">{plan.frequency}</td>
                    <td><span className={cn("badge", plan.is_active ? "badge-success" : "badge-neutral")}>{plan.is_active ? "Active" : "Inactive"}</span></td>
                    <td>
                      <div className="flex items-center gap-2">
                        <Link href={`/chitti/plans/${plan.id}`} className="btn-ghost btn-sm">View</Link>
                        <button onClick={() => handleDuplicate(plan.id)} className="btn-ghost btn-sm"><Copy size={12} /> Duplicate</button>
                        <button onClick={() => handleToggleActive(plan)} className={cn("btn-ghost btn-sm", plan.is_active ? "text-warning-600 hover:text-warning-700" : "text-success-600 hover:text-success-700")}>
                          {plan.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </div>
                    </td>
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
