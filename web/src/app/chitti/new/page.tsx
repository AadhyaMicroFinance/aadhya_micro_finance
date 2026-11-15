"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import NumericInput from "@/components/ui/NumericInput";
import { chittiApi, type ChittiPlan, type ChittiPreview } from "@/services/chitti";
import { getApiErrorMessage } from "@/services/api-client";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import { ArrowLeft, ArrowRight, CheckCircle2, Check, Plus, Sparkles } from "lucide-react";

type Step = 1 | 2;
type DirectRule = "FIXED" | "LIFT_BASED";

function todayIso(): string {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

function suggestedName(plan: ChittiPlan): string {
  const month = new Date().toLocaleDateString("en-IN", { month: "short", year: "numeric" });
  return `${plan.name} — ${month}`;
}

function numericValue(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Per-period contribution shown before creating, straight from the plan rules. */
function planContributionLabel(plan: ChittiPlan): string {
  const rules = (plan.contribution_rules ?? {}) as Record<string, unknown>;
  const type = String(rules.type || "FIXED");
  if (type === "FIXED" && rules.installment_amount) {
    return `${formatCurrency(Number(rules.installment_amount))} per member / period`;
  }
  if (type === "LIFT_BASED") {
    if (rules.regular_amount) {
      return `${formatCurrency(Number(rules.regular_amount))} regular + 1% of Chitti value from the period after lifting`;
    }
    return `${formatCurrency(Number(rules.pre_lift_amount || 0))} before lifting, ${formatCurrency(Number(rules.post_lift_amount || 0))} after (legacy plan)`;
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
    frequency: "",
    duration: "",
    contribution_amount: "",
    total_value: "",
    notes: "",
  });

  const [preview, setPreview] = useState<ChittiPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [directMode, setDirectMode] = useState(true);
  const [directRule, setDirectRule] = useState<DirectRule>("FIXED");
  const [winnerMethod, setWinnerMethod] = useState<"SCHEDULED" | "CUSTOM">("SCHEDULED");
  const [directForm, setDirectForm] = useState({ name: "", total_value: "", member_count: "", frequency: "MONTHLY", duration: "", start_date: todayIso(), installment: "", regular_lift_amount: "", custom_schedule: "1:1000", winner_schedule: "1:1", commission: "0", partial_payments_allowed: false });
  const [directPreview, setDirectPreview] = useState<ChittiPreview | null>(null);
  const previewGeneration = useRef(0);

  const fixedDirectTotal = numericValue(directForm.installment) * numericValue(directForm.member_count) * numericValue(directForm.duration);
  const livePlanMembers = numericValue(form.member_count || String(selectedPlan?.member_count || 0));
  const livePlanDuration = numericValue(form.duration || String(selectedPlan?.duration || 0));
  const livePlanContribution = numericValue(form.contribution_amount || String(
    selectedPlan?.contribution_rules.installment_amount ?? selectedPlan?.contribution_rules.regular_amount ?? selectedPlan?.contribution_rules.pre_lift_amount ?? ""
  ));
  const livePlanFixedTotal = livePlanMembers * livePlanDuration * livePlanContribution;

  const directPayload = () => {
    const contribution_rules = directRule === "FIXED"
      ? { type: "FIXED", installment_amount: Number(directForm.installment), partial_payments_allowed: directForm.partial_payments_allowed }
      : { type: "LIFT_BASED", regular_amount: Number(directForm.regular_lift_amount) };
    const payout_rules = winnerMethod === "SCHEDULED"
      ? { type: "SCHEDULED", payout_order: "MEMBER_NUMBER", commission_percentage: Number(directForm.commission) }
      : { type: "CUSTOM", payout_schedule: directForm.winner_schedule.split(",").map((part) => { const [period, member_number] = part.split(":").map(Number); return { period, member_number }; }), commission_percentage: Number(directForm.commission) };
    return {
      name: directForm.name.trim(), total_value: directRule === "FIXED" ? fixedDirectTotal : Number(directForm.total_value), member_count: Number(directForm.member_count),
      frequency: directForm.frequency, duration: Number(directForm.duration), start_date: directForm.start_date,
      chitti_type: directRule, contribution_rules,
      payout_rules,
    };
  };

  const previewDirect = async () => {
    setPreviewLoading(true); setError(null);
    try { setDirectPreview(await chittiApi.previewDirect(directPayload())); }
    catch (e) { setError(getApiErrorMessage(e, "Could not build the direct Chitti preview.")); }
    finally { setPreviewLoading(false); }
  };

  const createDirect = async () => {
    setCreating(true); setError(null);
    try {
      const chitti = await chittiApi.createChitti(directPayload());
      router.push(`/chitti/${chitti.id}#members`);
    } catch (e) { setError(getApiErrorMessage(e, "Could not create this Chitti.")); }
    finally { setCreating(false); }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const res = await chittiApi.listPlans({ per_page: 50, active_only: true });
        const supportedPlans = res.data.filter((plan) => ["FIXED", "LIFT_BASED"].includes(String((plan.contribution_rules as Record<string, unknown> | undefined)?.type || plan.chitti_type)));
        setPlans(supportedPlans);
        if (preselectedPlanId) {
          const plan = supportedPlans.find((p) => p.id === preselectedPlanId);
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
      frequency: prev.frequency || plan.frequency,
      duration: prev.duration || String(plan.duration),
      contribution_amount: prev.contribution_amount || String(
        plan.contribution_rules.installment_amount ?? plan.contribution_rules.regular_amount ?? plan.contribution_rules.pre_lift_amount ?? ""
      ),
      total_value: prev.total_value || String(plan.total_value),
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
        frequency: form.frequency || undefined,
        duration: form.duration ? parseInt(form.duration, 10) : undefined,
        total_value: selectedPlan.contribution_rules.type === "FIXED" ? undefined : Number(form.total_value || selectedPlan.total_value),
        contribution_rules: {
          ...selectedPlan.contribution_rules,
          ...(selectedPlan.contribution_rules.type === "FIXED"
            ? { installment_amount: Number(form.contribution_amount || selectedPlan.contribution_rules.installment_amount) }
            : { regular_amount: Number(form.contribution_amount || selectedPlan.contribution_rules.regular_amount) }),
        },
      });
      setPreview(result);
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not build the schedule preview."));
    } finally {
      setPreviewLoading(false);
    }
  };

  useEffect(() => {
    const plan = selectedPlan;
    if (!plan) return;
    const memberCount = numericValue(form.member_count || String(plan.member_count));
    const duration = numericValue(form.duration || String(plan.duration));
    const amount = numericValue(form.contribution_amount || String(
      plan.contribution_rules.installment_amount ?? plan.contribution_rules.regular_amount ?? plan.contribution_rules.pre_lift_amount ?? ""
    ));
    const totalValue = numericValue(form.total_value || String(plan.total_value));
    if (!form.start_date || memberCount < 1 || duration < 1 || amount <= 0 || (plan.contribution_rules.type !== "FIXED" && totalValue <= 0)) {
      setPreview(null);
      return;
    }
    const generation = ++previewGeneration.current;
    setDirectPreview(null);
    const timer = window.setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const rules = {
          ...plan.contribution_rules,
          ...(plan.contribution_rules.type === "FIXED" ? { installment_amount: amount } : { regular_amount: amount }),
        };
        const result = await chittiApi.previewPlan(plan.id, {
          start_date: form.start_date,
          member_count: memberCount,
          frequency: form.frequency || plan.frequency,
          duration,
          total_value: plan.contribution_rules.type === "FIXED" ? undefined : totalValue,
          contribution_rules: rules,
        });
        if (generation === previewGeneration.current) setPreview(result);
      } catch (e) {
        if (generation === previewGeneration.current) setError(getApiErrorMessage(e, "Could not build the schedule preview."));
      } finally {
        if (generation === previewGeneration.current) setPreviewLoading(false);
      }
    }, 300);
    return () => { window.clearTimeout(timer); previewGeneration.current += 1; };
  }, [selectedPlan, form.start_date, form.member_count, form.frequency, form.duration, form.contribution_amount, form.total_value]);

  useEffect(() => {
    if (step !== 1 || !directMode) return;
    const payload = directPayload();
    if (!payload.name || payload.member_count < 1 || payload.duration < 1 || !payload.start_date ||
        (directRule === "FIXED" ? numericValue(String(payload.contribution_rules.installment_amount)) <= 0 : payload.total_value <= 0)) {
      setDirectPreview(null);
      return;
    }
    const generation = ++previewGeneration.current;
    setDirectPreview(null);
    const timer = window.setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const result = await chittiApi.previewDirect(payload);
        if (generation === previewGeneration.current) setDirectPreview(result);
      } catch (e) {
        if (generation === previewGeneration.current) setError(getApiErrorMessage(e, "Could not build the direct Chitti preview."));
      } finally {
        if (generation === previewGeneration.current) setPreviewLoading(false);
      }
    }, 300);
    return () => { window.clearTimeout(timer); previewGeneration.current += 1; };
    // directPayload intentionally snapshots the current form values for this debounced request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, directMode, directRule, winnerMethod, directForm]);

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
        frequency: form.frequency || undefined,
        duration: form.duration ? parseInt(form.duration, 10) : undefined,
        total_value: selectedPlan.contribution_rules.type === "FIXED" ? undefined : Number(form.total_value || selectedPlan.total_value),
        contribution_rules: {
          ...selectedPlan.contribution_rules,
          ...(selectedPlan.contribution_rules.type === "FIXED"
            ? { installment_amount: Number(form.contribution_amount || selectedPlan.contribution_rules.installment_amount) }
            : { regular_amount: Number(form.contribution_amount || selectedPlan.contribution_rules.regular_amount) }),
        },
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

        {/* Direct creation uses the same validated strategies and calculator as saved plans. */}
        {step === 1 && <div className="card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Create directly</h2><p className="text-sm text-surface-500">Configure from the existing contribution and payout strategies.</p></div><button className="btn-secondary btn-sm" onClick={() => { setDirectMode(!directMode); setError(null); }}>{directMode ? "Use saved plan" : "Configure a new Chitti"}</button></div>
          {directMode && <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="text-sm">Chitti name<input className="input-field mt-1" value={directForm.name} onChange={(e) => setDirectForm({ ...directForm, name: e.target.value })} /></label>
              {directRule === "FIXED" ? <div className="text-sm">Total Chitti value<div className="input-field mt-1 bg-surface-50">{formatCurrency(fixedDirectTotal)}</div></div> : <label className="text-sm">Original Chitti value<NumericInput min="0.01" className="input-field mt-1" value={directForm.total_value} onValueChange={(value) => setDirectForm({ ...directForm, total_value: value })} /></label>}
              <label className="text-sm">Members<NumericInput integer min="1" className="input-field mt-1" value={directForm.member_count} onValueChange={(value) => setDirectForm({ ...directForm, member_count: value })} /></label>
              <label className="text-sm">Frequency<select className="input-field mt-1" value={directForm.frequency} onChange={(e) => setDirectForm({ ...directForm, frequency: e.target.value })}><option>DAILY</option><option>WEEKLY</option><option>MONTHLY</option></select></label>
              <label className="text-sm">Periods<NumericInput integer min="1" className="input-field mt-1" value={directForm.duration} onValueChange={(value) => setDirectForm({ ...directForm, duration: value })} /></label>
              <label className="text-sm">Start date<input type="date" className="input-field mt-1" value={directForm.start_date} onChange={(e) => setDirectForm({ ...directForm, start_date: e.target.value })} /></label>
              <fieldset className="text-sm sm:col-span-2"><legend>Chitti plan type</legend><div className="mt-2 grid gap-3 sm:grid-cols-2">{([{ id: "FIXED", label: "Fixed", detail: "Same contribution amount each period." }, { id: "LIFT_BASED", label: "Lift-based", detail: "Regular contribution plus the approved 1% surcharge after lifting." }] as const).map((option) => <label key={option.id} className={cn("flex cursor-pointer items-start gap-3 rounded-xl border p-3", directRule === option.id ? "border-brand-400 bg-brand-50" : "border-surface-200")}><input type="radio" name="chitti-plan-type" checked={directRule === option.id} onChange={() => { setDirectRule(option.id); setDirectPreview(null); }} /><span><strong>{option.label}</strong><span className="mt-1 block text-xs text-surface-500">{option.detail}</span></span></label>)}</div></fieldset>
              {directRule === "FIXED" && <label className="text-sm">Per member / period<NumericInput min="0.01" className="input-field mt-1" value={directForm.installment} onValueChange={(value) => setDirectForm({ ...directForm, installment: value })} /></label>}
              {directRule === "FIXED" && <label className="flex items-center gap-2 self-end pb-3 text-sm"><input type="checkbox" checked={directForm.partial_payments_allowed} onChange={(e) => setDirectForm({ ...directForm, partial_payments_allowed: e.target.checked })} />Allow partial contributions</label>}
              {directRule === "LIFT_BASED" && <><label className="text-sm">Regular contribution / period<NumericInput min="0.01" className="input-field mt-1" value={directForm.regular_lift_amount} onValueChange={(value) => setDirectForm({ ...directForm, regular_lift_amount: value })} /></label><p className="self-end rounded-lg bg-indigo-50 p-3 text-xs text-indigo-800">After an admin confirms a member lift, add 1% of the original Chitti value from the next period through the original final period.</p></>}
              <label className="text-sm">Winner selection<select className="input-field mt-1" value={winnerMethod} onChange={(e) => setWinnerMethod(e.target.value as "SCHEDULED" | "CUSTOM")}><option value="SCHEDULED">Scheduled by member number</option><option value="CUSTOM">Custom member per period</option></select></label>
              {winnerMethod === "CUSTOM" && <label className="text-sm sm:col-span-2">Winner schedule (period:member number)<input className="input-field mt-1" value={directForm.winner_schedule} onChange={(e) => setDirectForm({ ...directForm, winner_schedule: e.target.value })} placeholder="1:2,2:3,3:1" /></label>}
              <label className="text-sm">Scheduled payout commission %<NumericInput min="0" max="100" className="input-field mt-1" value={directForm.commission} onValueChange={(value) => setDirectForm({ ...directForm, commission: value })} /></label>
            </div>
            <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">Choose a Fixed or Lift-based Chitti. Scheduled payouts follow the saved payout order; no auction or unapproved winner calculation is applied here.</p>
            <div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={previewDirect} disabled={previewLoading}>{previewLoading ? "Calculating…" : "Preview financial schedule"}</button>{directPreview && <button className="btn-primary" onClick={createDirect} disabled={creating || previewLoading}>{creating ? "Creating…" : "Confirm and create Chitti"}</button>}</div>
            {directPreview && <div className="rounded-xl bg-surface-50 p-4"><h3 className="font-semibold">Review before creation</h3><p className="mt-2 text-sm">{directPreview.member_count} members · {directPreview.duration} periods · {directPreview.frequency} · Total value {formatCurrency(directPreview.total_value)}</p><p className="text-sm">Expected per period {formatCurrency(directPreview.periods[0]?.expected_collection || 0)} · Final due date {directPreview.periods[directPreview.periods.length - 1]?.due_date || "—"}</p><p className="text-sm">Expected contribution total {formatCurrency(directPreview.total_expected_collection)} · Expected payout total {formatCurrency(directPreview.total_expected_payout)}</p><div className="mt-3 max-h-56 overflow-auto"><table className="table"><thead><tr><th>Period</th><th>Due date</th><th>Expected collection</th></tr></thead><tbody>{directPreview.periods.map((period) => <tr key={period.period_number}><td>{period.period_number}</td><td>{period.due_date}</td><td>{formatCurrency(period.expected_collection)}</td></tr>)}</tbody></table></div></div>}
          </div>}
        </div>}

        {/* Step 1 — saved plans, retained for existing template workflows */}
        {step === 1 && !directMode && (
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
                  <NumericInput
                    integer
                    className="input-field"
                    value={form.member_count}
                    onValueChange={(value) => {
                      setForm({ ...form, member_count: value });
                      setPreview(null);
                    }}
                    placeholder={String(selectedPlan.member_count)}
                  />
                  <p className="mt-1 text-xs text-surface-500">
                    Plan default: {selectedPlan.member_count}. You can enroll fewer.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div><label className="label">Frequency</label><select className="input-field" value={form.frequency || selectedPlan.frequency} onChange={(e) => { setForm({ ...form, frequency: e.target.value }); setPreview(null); }}><option value="DAILY">Daily</option><option value="WEEKLY">Weekly</option><option value="BIWEEKLY">Bi-weekly</option><option value="MONTHLY">Monthly</option></select></div>
                <div><label className="label">Periods</label><NumericInput integer min="1" className="input-field" value={form.duration} onValueChange={(value) => { setForm({ ...form, duration: value }); setPreview(null); }} /></div>
                <div><label className="label">Contribution / member / period</label><NumericInput min="0.01" className="input-field" value={form.contribution_amount} onValueChange={(value) => { setForm({ ...form, contribution_amount: value }); setPreview(null); }} /></div>
                {selectedPlan.contribution_rules.type === "FIXED" ? <div><label className="label">Calculated Chitti value</label><div className="input-field bg-surface-50">{formatCurrency(numericValue(form.contribution_amount) * numericValue(form.member_count || String(selectedPlan.member_count)) * numericValue(form.duration || String(selectedPlan.duration)))}</div></div> : <div><label className="label">Original Chitti value</label><NumericInput min="0.01" className="input-field" value={form.total_value} onValueChange={(value) => { setForm({ ...form, total_value: value }); setPreview(null); }} /></div>}
              </div>
              <p className="text-xs text-surface-500">The preview shows each period’s expected total and final due date. Fixed total value is contribution × seats × periods; the saved plan remains unchanged.</p>
              <p className="rounded-lg bg-surface-50 p-3 text-sm">Expected contribution per period: <strong>{formatCurrency(livePlanMembers * livePlanContribution)}</strong>{selectedPlan.contribution_rules.type === "FIXED" && <> · Total Chitti value: <strong>{formatCurrency(livePlanFixedTotal)}</strong></>}{preview && <> · Final due date: <strong>{formatDate(preview.periods[preview.periods.length - 1]?.due_date)}</strong></>}</p>

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
                <p className="rounded-lg bg-brand-50 p-3 text-sm text-brand-800">Expected per period: <strong>{formatCurrency(preview.periods[0]?.expected_collection || 0)}</strong> · Final due date: <strong>{formatDate(preview.periods[preview.periods.length - 1]?.due_date)}</strong></p>

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
