"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { chittiApi, type ChittiPlan, type ChittiPreview } from "@/services/chitti";
import { reportApi, type ChittiPlanMetrics } from "@/services/reports";
import { formatCurrency, cn } from "@/lib/utils";
import {
  Handshake,
  Users,
  TrendingUp,
  TrendingDown,
  IndianRupee,
  Wallet,
} from "lucide-react";

export default function PlanDetailPage() {
  const params = useParams();
  const router = useRouter();
  const planId = params.id as string;

  const [plan, setPlan] = useState<ChittiPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<ChittiPreview | null>(null);
  const [previewDate, setPreviewDate] = useState("2026-09-15");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [metrics, setMetrics] = useState<ChittiPlanMetrics | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const p = await chittiApi.getPlan(planId);
        setPlan(p);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [planId]);

  useEffect(() => {
    const loadMetrics = async () => {
      try {
        const m = await reportApi.getChittiPlanMetrics(planId);
        setMetrics(m);
      } catch (e) {
        console.error(e);
      }
    };
    loadMetrics();
  }, [planId]);

  const handlePreview = async () => {
    setPreviewLoading(true);
    try {
      const result = await chittiApi.previewPlan(planId, {
        start_date: previewDate,
      });
      setPreview(result);
    } catch (e) {
      console.error(e);
    } finally {
      setPreviewLoading(false);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="card text-center py-8 text-gray-500">Loading...</div>
      </DashboardLayout>
    );
  }

  if (!plan) {
    return (
      <DashboardLayout>
        <div className="card text-center py-8 text-gray-500">Plan not found</div>
      </DashboardLayout>
    );
  }

  const contribRules = plan.contribution_rules as Record<string, unknown>;
  const payoutRules = plan.payout_rules as Record<string, unknown>;
  const penaltyRules = (plan.penalty_rules || {}) as Record<string, unknown>;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <Link href="/chitti/plans" className="text-gray-400 hover:text-gray-600">
                ← Back
              </Link>
              <h2 className="text-2xl font-bold text-gray-900">{plan.name}</h2>
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  plan.is_active ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-800"
                }`}
              >
                {plan.is_active ? "Active" : "Inactive"}
              </span>
            </div>
            <p className="text-sm text-gray-500">{plan.plan_code} • {plan.chitti_type} Plan</p>
          </div>
          <Link
            href={`/chitti/new?plan_id=${plan.id}`}
            className="btn-primary"
          >
            + Create Chitti from this Plan
          </Link>
        </div>

        {/* Plan Performance Metrics */}
        {metrics && metrics.total_chittis > 0 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="rounded-xl bg-brand-50 p-2 text-brand-600">
                <TrendingUp size={16} />
              </div>
              <h3 className="text-sm font-semibold text-surface-900">
                Plan Performance
              </h3>
              <span className="badge-neutral">
                {metrics.total_chittis} chitti{metrics.total_chittis !== 1 ? "s" : ""}
              </span>
            </div>

            {/* Headline gradient stats */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-500 via-brand-600 to-indigo-600 p-5 shadow-elevated">
                <div className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-white/20 blur-2xl" />
                <div className="relative flex items-start justify-between">
                  <div className="space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-white/80">Total Members</p>
                    <p className="text-2xl font-bold text-white tabular-nums">{metrics.total_members}</p>
                  </div>
                  <div className="rounded-2xl bg-white/20 p-2.5 text-white"><Users size={20} /></div>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-success-500 via-emerald-600 to-teal-600 p-5 shadow-elevated">
                <div className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-white/20 blur-2xl" />
                <div className="relative flex items-start justify-between">
                  <div className="space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-white/80">Collected</p>
                    <p className="text-2xl font-bold text-white tabular-nums">{formatCurrency(Number(metrics.total_collected))}</p>
                  </div>
                  <div className="rounded-2xl bg-white/20 p-2.5 text-white"><Wallet size={20} /></div>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-warning-500 via-orange-500 to-amber-600 p-5 shadow-elevated">
                <div className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-white/20 blur-2xl" />
                <div className="relative flex items-start justify-between">
                  <div className="space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-white/80">Pending</p>
                    <p className="text-2xl font-bold text-white tabular-nums">{formatCurrency(Number(metrics.total_pending))}</p>
                  </div>
                  <div className="rounded-2xl bg-white/20 p-2.5 text-white"><TrendingDown size={20} /></div>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-500 via-purple-600 to-fuchsia-600 p-5 shadow-elevated">
                <div className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-white/20 blur-2xl" />
                <div className="relative flex items-start justify-between">
                  <div className="space-y-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-white/80">Payouts</p>
                    <p className="text-2xl font-bold text-white tabular-nums">{formatCurrency(Number(metrics.total_payouts))}</p>
                  </div>
                  <div className="rounded-2xl bg-white/20 p-2.5 text-white"><IndianRupee size={20} /></div>
                </div>
              </div>
            </div>

            {/* Collection rate + status breakdown */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="card lg:col-span-2">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-semibold text-surface-900">Collection Rate</h4>
                  <span className="text-sm font-bold text-brand-600">{metrics.collection_rate}%</span>
                </div>
                <div className="h-3 w-full rounded-full bg-surface-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-brand-500 to-indigo-500 transition-all duration-700"
                    style={{ width: `${Math.min(metrics.collection_rate, 100)}%` }}
                  />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-center">
                  <div className="rounded-xl bg-brand-50 p-3">
                    <p className="text-[11px] font-medium text-brand-600 uppercase">Total Expected</p>
                    <p className="text-sm font-bold text-brand-700">{formatCurrency(Number(metrics.total_expected))}</p>
                  </div>
                  <div className="rounded-xl bg-purple-50 p-3">
                    <p className="text-[11px] font-medium text-purple-600 uppercase">Total Value Pool</p>
                    <p className="text-sm font-bold text-purple-700">{formatCurrency(plan.total_value)}</p>
                  </div>
                </div>
              </div>

              <div className="card">
                <h4 className="text-sm font-semibold text-surface-900 mb-3">By Status</h4>
                <div className="space-y-2">
                  {Object.entries(metrics.by_status).map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between">
                      <span className={cn("badge", status === "RUNNING" ? "badge-brand" : status === "COMPLETED" ? "badge-success" : status === "PAUSED" ? "badge-info" : "badge-warning")}>
                        {status}
                      </span>
                      <span className="text-sm font-bold text-surface-900">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Plan Details Grid */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Basic Info */}
          <div className="card">
            <h3 className="mb-4 text-lg font-semibold text-gray-800">Plan Details</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Total Value</span>
                <span className="text-sm font-medium">{formatCurrency(plan.total_value)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Members</span>
                <span className="text-sm font-medium">{plan.member_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Frequency</span>
                <span className="text-sm font-medium">{plan.frequency}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Duration</span>
                <span className="text-sm font-medium">{plan.duration} periods</span>
              </div>
              {plan.description && (
                <div className="pt-2 border-t border-gray-100">
                  <p className="text-sm text-gray-500">Description</p>
                  <p className="text-sm mt-1">{plan.description}</p>
                </div>
              )}
            </div>
          </div>

          {/* Contribution Rules */}
          <div className="card">
            <h3 className="mb-4 text-lg font-semibold text-gray-800">Contribution Rules</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Rule Type</span>
                <span className="text-sm font-medium">{String(contribRules.type ?? "—")}</span>
              </div>
              {!!contribRules.installment_amount && (
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Installment</span>
                  <span className="text-sm font-medium">
                    {formatCurrency(Number(contribRules.installment_amount))}
                  </span>
                </div>
              )}
              {contribRules.partial_payments_allowed !== undefined && (
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Partial Payments</span>
                  <span className="text-sm font-medium">
                    {contribRules.partial_payments_allowed ? "Allowed" : "Not Allowed"}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Payout Rules */}
          <div className="card">
            <h3 className="mb-4 text-lg font-semibold text-gray-800">Payout Rules</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Payout Type</span>
                <span className="text-sm font-medium">{String(payoutRules.type ?? "—")}</span>
              </div>
              {!!payoutRules.payout_order && (
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Order</span>
                  <span className="text-sm font-medium">{String(payoutRules.payout_order)}</span>
                </div>
              )}
              {payoutRules.commission_percentage !== undefined && (
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Commission</span>
                  <span className="text-sm font-medium">{String(payoutRules.commission_percentage)}%</span>
                </div>
              )}
            </div>
          </div>

          {/* Penalty Rules */}
          <div className="card">
            <h3 className="mb-4 text-lg font-semibold text-gray-800">Penalty Rules</h3>
            <div className="space-y-3">
              {penaltyRules.grace_period_days !== undefined ? (
                <>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Grace Period</span>
                    <span className="text-sm font-medium">{String(penaltyRules.grace_period_days)} days</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Penalty</span>
                    <span className="text-sm font-medium">
                      {formatCurrency(Number(penaltyRules.penalty_amount || 0))} / day
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Type</span>
                    <span className="text-sm font-medium">{String(penaltyRules.penalty_type || "N/A")}</span>
                  </div>
                </>
              ) : (
                <p className="text-sm text-gray-500">No penalty rules configured</p>
              )}
            </div>
          </div>
        </div>

        {/* Preview Section */}
        <div className="card">
          <h3 className="mb-4 text-lg font-semibold text-gray-800">Preview Schedule</h3>
          <div className="flex items-end gap-4 mb-4">
            <div>
              <label className="mb-1 block text-sm font-medium">Start Date</label>
              <input
                type="date"
                value={previewDate}
                onChange={(e) => setPreviewDate(e.target.value)}
                className="input-field"
              />
            </div>
            <button
              onClick={handlePreview}
              disabled={previewLoading}
              className="btn-primary"
            >
              {previewLoading ? "Generating..." : "Generate Preview"}
            </button>
          </div>

          {preview && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs text-gray-500">Total Expected Collection</p>
                  <p className="text-lg font-bold text-gray-900">
                    {formatCurrency(preview.total_expected_collection)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Periods</p>
                  <p className="text-lg font-bold text-gray-900">{preview.periods.length}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Total Value</p>
                  <p className="text-lg font-bold text-gray-900">
                    {formatCurrency(preview.total_value)}
                  </p>
                </div>
              </div>

              {/* Check if lift-based (array of member schedules) */}
              {Array.isArray(preview.per_member_installment_schedule) &&
              preview.per_member_installment_schedule.length > 0 &&
              "member_number" in preview.per_member_installment_schedule[0] ? (
                // Lift-based preview: show sample member schedules
                <div className="space-y-4">
                  <p className="text-sm font-medium text-gray-700">
                    🏆 Lift Based Schedule — Sample member schedules:
                  </p>
                  {(preview.per_member_installment_schedule as unknown as {
                    member_number: number;
                    lift_period: number;
                    schedule: { period: number; due_date: string; amount: number }[];
                    total: number;
                  }[]).map((memberSchedule) => (
                    <div key={memberSchedule.member_number} className="rounded-lg border border-gray-200 p-4">
                      <div className="mb-3 flex items-center justify-between">
                        <h4 className="font-medium text-gray-800">
                          Member #{memberSchedule.member_number}
                        </h4>
                        <span className="text-sm text-gray-500">
                          Lifts in period {memberSchedule.lift_period} • Total: {formatCurrency(memberSchedule.total)}
                        </span>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="border-b border-gray-200 text-gray-500">
                            <tr>
                              <th className="px-2 py-1">Period</th>
                              <th className="px-2 py-1">Due Date</th>
                              <th className="px-2 py-1">Amount</th>
                              <th className="px-2 py-1">Type</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-50">
                            {memberSchedule.schedule.slice(0, 8).map((s) => (
                              <tr key={s.period}>
                                <td className="px-2 py-1">{s.period}</td>
                                <td className="px-2 py-1">{s.due_date}</td>
                                <td className="px-2 py-1 font-medium">{formatCurrency(s.amount)}</td>
                                <td className="px-2 py-1">
                                  {s.period < memberSchedule.lift_period ? (
                                    <span className="text-blue-600">Pre-Lift</span>
                                  ) : s.period === memberSchedule.lift_period ? (
                                    <span className="text-green-600 font-medium">🏆 Lift</span>
                                  ) : (
                                    <span className="text-orange-600">Post-Lift</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {memberSchedule.schedule.length > 8 && (
                          <p className="mt-1 text-xs text-gray-400">
                            ...{memberSchedule.schedule.length - 8} more periods
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                // Standard preview: flat installment schedule
                <div className="space-y-2">
                  <div className="flex items-center gap-4">
                    <p className="text-xs text-gray-500">Per Member / Period:</p>
                    <p className="text-sm font-bold text-gray-900">
                      {(preview.per_member_installment_schedule as { period: number; due_date: string; amount: number }[])[0]
                        ? formatCurrency(
                            (preview.per_member_installment_schedule as { period: number; due_date: string; amount: number }[])[0].amount
                          )
                        : "—"}
                    </p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="border-b border-gray-200 text-xs font-medium uppercase text-gray-500">
                        <tr>
                          <th className="px-3 py-2">Period</th>
                          <th className="px-3 py-2">Due Date</th>
                          <th className="px-3 py-2">Per Member</th>
                          <th className="px-3 py-2">Total Collection</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {preview.periods.slice(0, 10).map((p) => (
                          <tr key={p.period_number}>
                            <td className="px-3 py-2">{p.period_number}</td>
                            <td className="px-3 py-2">{p.due_date}</td>
                            <td className="px-3 py-2">
                              {formatCurrency(
                                (preview.per_member_installment_schedule as { period: number; due_date: string; amount: number }[])[p.period_number - 1]?.amount || 0
                              )}
                            </td>
                            <td className="px-3 py-2">{formatCurrency(p.expected_collection)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {preview.periods.length > 10 && (
                      <p className="mt-2 text-center text-sm text-gray-500">
                        ...and {preview.periods.length - 10} more periods
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
