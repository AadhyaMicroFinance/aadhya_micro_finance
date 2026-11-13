"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { chittiApi, type ChittiPlan, type ChittiPreview } from "@/services/chitti";
import { getApiErrorMessage } from "@/services/api-client";
import { formatCurrency, cn } from "@/lib/utils";
import { ArrowLeft, ArrowRight, CheckCircle2, Check, Plus, Sparkles } from "lucide-react";

type Step = 1 | 2;

function todayIso(): string {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

function suggestedName(plan: ChittiPlan): string {
  const month = new Date().toLocaleDateString("en-IN", { month: "short", year: "numeric" });
  return `${plan.name} — ${month}`;
}

/** Per-period contribution shown before creating, straight from the plan rules. */
function planContributionLabel(plan: ChittiPlan): string {
  const rules = (plan.contribution_rules ?? {}) as Record<string, unknown>;
  const type = String(rules.type || "FIXED");
  if (type === "FIXED" && rules.installment_amount) {
    return `${formatCurrency(Number(rules.installment_amount))} per member / period`;
  }
  if (type === "LIFT_BASED") {
    return `${formatCurrency(Number(rules.pre_lift_amount || 0))} before lifting, ${formatCurrency(Number(rules.post_lift_amount || 0))} after`;
  }
  return "Custom schedule";
}

function NewChittiForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedPlanId = searchParams.get("plan_id");

  const [step, setStep] = useState<Step>(preselectedPlanId ? 2 : 1);
  const [plans, setPlans] = useState<ChittiPlan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<ChittiPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: "",
    branch: "",
    start_date: todayIso(),
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
          if (plan) choosePlan(plan);
        }
      } catch (e) {
        setError(getApiErrorMessage(e, "Could not load chitti plans."));
      } finally {
        setLoading(false);
      }
    };
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preselectedPlanId]);

  /** Selecting a plan fills everything we already know, so nothing is re-typed. */
  const choosePlan = (plan: ChittiPlan) => {
    setSelectedPlan(plan);
    setForm((prev) => ({
      ...prev,
      name: prev.name || suggestedName(plan),
      member_count: prev.member_count || String(plan.member_count),
    }));
    setPreview(null);
    setError(null);
    setStep(2);
  };

  const generatePreview = async () => {
    if (!selectedPlan) return;
    setPreviewLoading(true);
    setError(null);
    try {
      const result = await chittiApi.previewPlan(selectedPlan.id, {
        start_date: form.start_date,
        member_count: form.member_count ? parseInt(form.member_count) : undefined,
      });
      setPreview(result);
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not build the schedule preview."));
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!selectedPlan) return;
    if (!form.name.trim()) {
      setError("Give the chitti a name so your team can recognise it.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const chitti = await chittiApi.createChitti({
        plan_id: selectedPlan.id,
        name: form.name.trim(),
        branch: form.branch || undefined,
        start_date: form.start_date,
        member_count: form.member_count ? parseInt(form.member_count) : undefined,
        notes: form.notes || undefined,
      });
      // Straight to adding members — the next thing that has to happen.
      router.push(`/chitti/${chitti.id}#members`);
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not create this chitti."));
    } finally {
      setCreating(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-tight text-surface-900 sm:text-2xl">
              New chitti
            </h1>
            <p className="mt-1 text-sm leading-snug text-surface-500">
              Pick a plan, check the name and start date, then add members. It saves as a
              draft — nothing is collected until you start it.
            </p>
          </div>
          <Link href="/chitti" className="btn-secondary w-full sm:w-auto">
            <ArrowLeft size={16} /> Back to workspace
          </Link>
        </div>

        {/* Two steps, always visible */}
        <ol className="flex flex-wrap items-center gap-2 text-xs sm:gap-3 sm:text-sm">
          {[
            { n: 1, label: "Choose a plan" },
            { n: 2, label: "Name, date & create" },
          ].map((s, index) => (
            <li key={s.n} className="flex items-center gap-2">
              <span
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold",
                  step >= s.n ? "bg-brand-600 text-white" : "bg-surface-200 text-surface-500"
                )}
              >
                {step > s.n ? <Check size={14} /> : s.n}
              </span>
              <span className={cn(step >= s.n ? "font-semibold text-surface-900" : "text-surface-500")}>
                {s.label}
              </span>
              {index === 0 && <span className="mx-1 hidden h-px w-6 bg-surface-200 sm:block sm:w-8" />}
            </li>
          ))}
        </ol>

        {error && (
          <div className="rounded-xl border border-danger-100 bg-danger-50 px-4 py-3 text-sm text-danger-700">
            {error}
          </div>
        )}

        {/* Step 1 — plans */}
        {step === 1 && (
          <div className="card">
            <h2 className="text-base font-semibold text-surface-900">Choose a chitti plan</h2>
            <p className="mt-0.5 text-sm text-surface-500">
              A plan sets the amount, duration and payout rules. Everything can be reviewed
              after you pick it.
            </p>

            {loading ? (
              <p className="mt-4 text-sm text-surface-500">Loading plans…</p>
            ) : plans.length === 0 ? (
              <div className="mt-4 rounded-xl border border-surface-100 p-6 text-center">
                <p className="font-medium text-surface-900">No active plans yet</p>
                <p className="mt-1 text-sm text-surface-500">
                  Create a plan first, then come back here to start a chitti from it.
                </p>
                <Link href="/chitti/plans/new" className="btn-primary mt-4 inline-flex">
                  <Plus size={16} /> Create a plan
                </Link>
              </div>
            ) : (
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {plans.map((plan) => (
                  <button
                    key={plan.id}
                    onClick={() => choosePlan(plan)}
                    className={cn(
                      "rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-md",
                      selectedPlan?.id === plan.id
                        ? "border-brand-400 bg-brand-50/50"
                        : "border-surface-200 bg-white"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-semibold text-surface-900">{plan.name}</p>
                        <p className="text-xs text-surface-500">
                          {plan.plan_code} • {plan.chitti_type} • {plan.frequency.toLowerCase()}
                        </p>
                      </div>
                      <span className="badge badge-brand">{plan.duration} periods</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <p className="text-[10px] uppercase text-surface-400">Value</p>
                        <p className="font-bold text-surface-900">{formatCurrency(plan.total_value)}</p>
                      </div>
                      <div>
                        <p className="text-[10px] uppercase text-surface-400">Members</p>
                        <p className="font-bold text-surface-900">{plan.member_count}</p>
                      </div>
                    </div>
                    <p className="mt-2 text-xs text-surface-500">{planContributionLabel(plan)}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 2 — details + create */}
        {step === 2 && selectedPlan && (
          <div className="space-y-4">
            <div className="card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-surface-900">
                    {selectedPlan.name}
                  </h2>
                  <p className="text-sm text-surface-500">
                    {formatCurrency(selectedPlan.total_value)} • {selectedPlan.member_count} seats •{" "}
                    {selectedPlan.duration} {selectedPlan.frequency.toLowerCase()} periods
                  </p>
                  <p className="mt-1 text-xs text-surface-500">
                    {planContributionLabel(selectedPlan)}
                  </p>
                </div>
                <button onClick={() => setStep(1)} className="btn-secondary btn-sm">
                  Change plan
                </button>
              </div>
            </div>

            <div className="card space-y-4">
              <h2 className="text-base font-semibold text-surface-900">Name and dates</h2>

              <div>
                <label className="label">Chitti name</label>
                <input
                  className="input-field"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Hyderabad Weekly — Nov 2026"
                  autoFocus
                />
                <p className="mt-1 text-xs text-surface-500">
                  Pre-filled for you — change it if your team uses another naming style.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="label">First due date</label>
                  <input
                    type="date"
                    className="input-field"
                    value={form.start_date}
                    onChange={(e) => {
                      setForm({ ...form, start_date: e.target.value });
                      setPreview(null);
                    }}
                  />
                  <p className="mt-1 text-xs text-surface-500">
                    Defaults to today. Period 1 is due on this date.
                  </p>
                </div>
                <div>
                  <label className="label">Seats</label>
                  <input
                    type="number"
                    className="input-field"
                    value={form.member_count}
                    onChange={(e) => {
                      setForm({ ...form, member_count: e.target.value });
                      setPreview(null);
                    }}
                    placeholder={String(selectedPlan.member_count)}
                  />
                  <p className="mt-1 text-xs text-surface-500">
                    Plan default: {selectedPlan.member_count}. You can enroll fewer.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="label">Branch (optional)</label>
                  <input
                    className="input-field"
                    value={form.branch}
                    onChange={(e) => setForm({ ...form, branch: e.target.value })}
                    placeholder="e.g. Hyderabad"
                  />
                </div>
                <div>
                  <label className="label">Notes (optional)</label>
                  <input
                    className="input-field"
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    placeholder="Anything the team should know"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-3 border-t border-surface-100 pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                <button
                  onClick={generatePreview}
                  disabled={previewLoading}
                  className="btn-secondary btn-sm w-full sm:w-auto"
                >
                  <Sparkles size={14} />
                  {previewLoading ? "Building…" : preview ? "Refresh schedule preview" : "Preview schedule"}
                </button>
                {/* Primary action first on a phone, side by side on larger screens. */}
                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center">
                  <button onClick={() => setStep(1)} className="btn-secondary w-full sm:w-auto">
                    Back
                  </button>
                  <button
                    onClick={handleCreate}
                    disabled={creating || !form.name.trim()}
                    className="btn-primary w-full sm:w-auto"
                  >
                    {creating ? "Creating…" : "Create chitti & add members"}
                    {!creating && <ArrowRight size={16} />}
                  </button>
                </div>
              </div>
            </div>

            {/* Optional schedule preview — never required to create */}
            {preview && (
              <div className="card space-y-4">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-success-600" />
                  <h2 className="text-base font-semibold text-surface-900">Schedule preview</h2>
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-xl bg-surface-50 p-3">
                    <p className="text-[10px] uppercase text-surface-400">Members</p>
                    <p className="text-sm font-bold">{preview.member_count}</p>
                  </div>
                  <div className="rounded-xl bg-surface-50 p-3">
                    <p className="text-[10px] uppercase text-surface-400">Periods</p>
                    <p className="text-sm font-bold">{preview.duration}</p>
                  </div>
                  <div className="rounded-xl bg-surface-50 p-3">
                    <p className="text-[10px] uppercase text-surface-400">Total collection</p>
                    <p className="text-sm font-bold">{formatCurrency(preview.total_expected_collection)}</p>
                  </div>
                  <div className="rounded-xl bg-surface-50 p-3">
                    <p className="text-[10px] uppercase text-surface-400">Total payout</p>
                    <p className="text-sm font-bold">{formatCurrency(preview.total_expected_payout)}</p>
                  </div>
                </div>

                {Array.isArray(preview.per_member_installment_schedule) &&
                preview.per_member_installment_schedule.length > 0 &&
                "member_number" in (preview.per_member_installment_schedule[0] || {}) ? (
                  <p className="rounded-xl bg-brand-50 p-3 text-sm text-brand-800">
                    Lift-based plan: each member&apos;s amount changes after they lift. The full
                    member-wise schedule is created automatically when the chitti starts.
                  </p>
                ) : (
                  <>
                    <div className="space-y-2 sm:hidden">
                      {preview.periods.slice(0, 8).map((p) => (
                        <div
                          key={p.period_number}
                          className="flex items-center justify-between gap-3 rounded-xl border border-surface-100 p-3"
                        >
                          <div className="min-w-0">
                            <p className="text-sm font-semibold text-surface-900">Period {p.period_number}</p>
                            <p className="text-[11px] text-surface-500">{p.due_date}</p>
                          </div>
                          <div className="shrink-0 text-right">
                            <p className="text-sm font-semibold text-surface-900">
                              {formatCurrency(p.expected_collection)}
                            </p>
                            <p className="text-[11px] text-surface-500">
                              {formatCurrency(
                                (
                                  preview.per_member_installment_schedule as {
                                    period: number;
                                    amount: number;
                                  }[]
                                )[p.period_number - 1]?.amount || 0
                              )}{" "}
                              / member
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="hidden overflow-x-auto sm:block">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Period</th>
                            <th>Due date</th>
                            <th>Per member</th>
                            <th>Total collection</th>
                          </tr>
                        </thead>
                        <tbody>
                          {preview.periods.slice(0, 8).map((p) => (
                            <tr key={p.period_number}>
                              <td>{p.period_number}</td>
                              <td>{p.due_date}</td>
                              <td>
                                {formatCurrency(
                                  (
                                    preview.per_member_installment_schedule as {
                                      period: number;
                                      amount: number;
                                    }[]
                                  )[p.period_number - 1]?.amount || 0
                                )}
                              </td>
                              <td className="font-medium">{formatCurrency(p.expected_collection)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            )}
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
          <div className="p-4 text-sm text-surface-500 sm:p-8">Loading…</div>
        </DashboardLayout>
      }
    >
      <NewChittiForm />
    </Suspense>
  );
}
