"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { chittiApi, type ChittiPlan, type ChittiPreview } from "@/services/chitti";
import { formatCurrency } from "@/lib/utils";

type Step = 1 | 2 | 3 | 4;

function NewChittiForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedPlanId = searchParams.get("plan_id");

  const [step, setStep] = useState<Step>(preselectedPlanId ? 2 : 1);
  const [plans, setPlans] = useState<ChittiPlan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<ChittiPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const [form, setForm] = useState({
    name: "",
    branch: "",
    start_date: "2026-09-15",
    member_count: "",
    notes: "",
  });

  const [preview, setPreview] = useState<ChittiPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await chittiApi.listPlans({ per_page: 50, active_only: true });
        setPlans(res.data);
        if (preselectedPlanId) {
          const plan = res.data.find((p) => p.id === preselectedPlanId);
          if (plan) setSelectedPlan(plan);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [preselectedPlanId]);

  const generatePreview = async () => {
    if (!selectedPlan) return;
    setPreviewLoading(true);
    try {
      const mc = form.member_count ? parseInt(form.member_count) : undefined;
      const result = await chittiApi.previewPlan(selectedPlan.id, {
        start_date: form.start_date,
        member_count: mc,
      });
      setPreview(result);
      setStep(3);
    } catch (e) {
      console.error(e);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!selectedPlan) return;
    setCreating(true);
    try {
      const chitti = await chittiApi.createChitti({
        plan_id: selectedPlan.id,
        name: form.name,
        branch: form.branch || undefined,
        start_date: form.start_date,
        member_count: form.member_count ? parseInt(form.member_count) : undefined,
        notes: form.notes || undefined,
      });
      router.push(`/chitti/${chitti.id}`);
    } catch (e) {
      console.error(e);
    } finally {
      setCreating(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-4xl mx-auto">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Create Chitti</h2>
          <p className="text-sm text-gray-500">Set up a new chitti from an existing plan</p>
        </div>

        {/* Progress Steps */}
        <div className="flex items-center gap-4">
          {[
            { num: 1, label: "Select Plan" },
            { num: 2, label: "Details" },
            { num: 3, label: "Review" },
            { num: 4, label: "Create" },
          ].map((s) => (
            <div key={s.num} className="flex items-center gap-2">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium ${
                  step >= s.num
                    ? "bg-primary-600 text-white"
                    : "bg-gray-200 text-gray-500"
                }`}
              >
                {s.num}
              </div>
              <span
                className={`text-sm ${
                  step >= s.num ? "text-gray-900 font-medium" : "text-gray-500"
                }`}
              >
                {s.label}
              </span>
              {s.num < 4 && <div className="w-8 border-t border-gray-300" />}
            </div>
          ))}
        </div>

        {/* Step 1: Select Plan */}
        {step === 1 && (
          <div className="card">
            <h3 className="mb-4 text-lg font-semibold">Select a Chitti Plan</h3>
            {loading ? (
              <p className="text-gray-500">Loading plans...</p>
            ) : plans.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-500">No active plans. Create a plan first.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {plans.map((plan) => (
                  <div
                    key={plan.id}
                    onClick={() => {
                      setSelectedPlan(plan);
                      setStep(2);
                    }}
                    className={`cursor-pointer rounded-lg border-2 p-4 transition-colors ${
                      selectedPlan?.id === plan.id
                        ? "border-primary-500 bg-primary-50"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="font-medium text-gray-900">{plan.name}</h4>
                        <p className="text-sm text-gray-500">
                          {plan.plan_code} • {plan.chitti_type} • {plan.frequency}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-bold text-gray-900">{formatCurrency(plan.total_value)}</p>
                        <p className="text-sm text-gray-500">
                          {plan.member_count} members • {plan.duration} periods
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 2: Chitti Details */}
        {step === 2 && selectedPlan && (
          <div className="card">
            <h3 className="mb-4 text-lg font-semibold">Chitti Details</h3>
            <div className="mb-4 p-3 bg-gray-50 rounded-lg">
              <p className="text-sm font-medium text-gray-700">
                Selected Plan: {selectedPlan.name} ({selectedPlan.plan_code})
              </p>
              <p className="text-sm text-gray-500">
                {formatCurrency(selectedPlan.total_value)} • {selectedPlan.member_count} members • {selectedPlan.frequency}
              </p>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium">Chitti Name *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="input-field"
                  placeholder="e.g., Hyderabad Weekly - Sep 2026"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">Start Date *</label>
                  <input
                    type="date"
                    value={form.start_date}
                    onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                    className="input-field"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Branch (optional)</label>
                  <input
                    type="text"
                    value={form.branch}
                    onChange={(e) => setForm({ ...form, branch: e.target.value })}
                    className="input-field"
                    placeholder="e.g., Hyderabad"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">
                  Member Count (default: {selectedPlan.member_count})
                </label>
                <input
                  type="number"
                  value={form.member_count}
                  onChange={(e) => setForm({ ...form, member_count: e.target.value })}
                  className="input-field"
                  placeholder={String(selectedPlan.member_count)}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  className="input-field"
                  rows={2}
                  placeholder="Optional notes"
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setStep(1)} className="btn-secondary">
                Back
              </button>
              <button
                onClick={async () => {
                  if (!form.name) return;
                  await generatePreview();
                }}
                disabled={!form.name || previewLoading}
                className="btn-primary"
              >
                {previewLoading ? "Generating Preview..." : "Preview Schedule →"}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Review */}
        {step === 3 && preview && (
          <div className="card">
            <h3 className="mb-4 text-lg font-semibold">Review & Confirm</h3>
            <div className="grid grid-cols-2 gap-6 mb-6">
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Chitti Name</span>
                  <span className="font-medium">{form.name}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Plan</span>
                  <span className="font-medium">{preview.plan_name}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Type</span>
                  <span className="font-medium">{preview.chitti_type}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Frequency</span>
                  <span className="font-medium">{preview.frequency}</span>
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Total Value</span>
                  <span className="font-medium">{formatCurrency(preview.total_value)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Members</span>
                  <span className="font-medium">{preview.member_count}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Duration</span>
                  <span className="font-medium">{preview.duration} periods</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Start Date</span>
                  <span className="font-medium">{form.start_date}</span>
                </div>
              </div>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg mb-6">
              <div className="grid grid-cols-2 gap-4">
                <p className="text-sm text-gray-600">
                  Total expected collection:{" "}
                  <span className="font-bold text-gray-900">
                    {formatCurrency(preview.total_expected_collection)}
                  </span>
                </p>
                {Array.isArray(preview.per_member_installment_schedule) &&
                preview.per_member_installment_schedule.length > 0 &&
                "member_number" in (preview.per_member_installment_schedule[0] || {}) ? (
                  <p className="text-sm text-gray-600">
                    Lift Based: {preview.member_count} members • Different amounts before/after lift
                  </p>
                ) : (
                  <p className="text-sm text-gray-600">
                    Per member per period:{" "}
                    <span className="font-bold text-gray-900">
                      {preview.per_member_installment_schedule[0]
                        ? formatCurrency((preview.per_member_installment_schedule[0] as { amount: number }).amount)
                        : "—"}
                    </span>
                  </p>
                )}
              </div>
            </div>

            {/* Lift-based schedule preview */}
            {Array.isArray(preview.per_member_installment_schedule) &&
            preview.per_member_installment_schedule.length > 0 &&
            "member_number" in (preview.per_member_installment_schedule[0] || {}) ? (
              <div className="space-y-3">
                <h4 className="font-medium text-gray-800">🏆 Lift Based Schedule (sample members)</h4>
                {(preview.per_member_installment_schedule as unknown as {
                  member_number: number;
                  lift_period: number;
                  schedule: { period: number; due_date: string; amount: number }[];
                  total: number;
                }[]).map((ms) => (
                  <div key={ms.member_number} className="rounded border p-3">
                    <p className="text-sm font-medium">
                      Member #{ms.member_number}: Lifts period {ms.lift_period} • Total {formatCurrency(ms.total)}
                    </p>
                    <div className="mt-2 flex gap-2 flex-wrap text-xs">
                      {ms.schedule.slice(0, 6).map((s) => (
                        <span key={s.period} className="rounded bg-gray-100 px-2 py-1">
                          P{s.period}: {formatCurrency(s.amount)}
                          {s.period === ms.lift_period && " 🏆"}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <>
                <h4 className="mb-3 font-medium text-gray-800">Schedule Preview (first 5 periods)</h4>
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
                      {preview.periods.slice(0, 5).map((p) => (
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
                </div>
              </>
            )}

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setStep(2)} className="btn-secondary">
                Back
              </button>
              <button onClick={handleCreate} disabled={creating} className="btn-primary">
                {creating ? "Creating..." : "✓ Create Chitti"}
              </button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}

// useSearchParams() must sit under a Suspense boundary so the route can be
// prerendered at build time (Next.js 14 requirement).
export default function NewChittiPage() {
  return (
    <Suspense
      fallback={
        <DashboardLayout>
          <div className="p-8 text-sm text-surface-500">Loading…</div>
        </DashboardLayout>
      }
    >
      <NewChittiForm />
    </Suspense>
  );
}
