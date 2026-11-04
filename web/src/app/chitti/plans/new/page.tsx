"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { chittiApi } from "@/services/chitti";

interface PlanField {
  id: string;
  label: string;
  value: string;
  type: "currency" | "percentage" | "number" | "text" | "select";
  options?: string[];
}

interface CustomScheduleRow {
  period: number;
  amount: string;
}

const CALC_METHODS = [
  {
    id: "FIXED",
    label: "Fixed Amount",
    description: "Same installment amount every period",
    fields: [{ label: "Installment Amount", key: "installment_amount", type: "currency" as const }],
  },
  {
    id: "LIFT_BASED",
    label: "Lift Based",
    description: "Different amounts before and after lifting",
    fields: [
      { label: "Before Lifting Amount", key: "pre_lift_amount", type: "currency" as const },
      { label: "After Lifting Amount", key: "post_lift_amount", type: "currency" as const },
    ],
  },
  {
    id: "CUSTOM",
    label: "Custom Schedule",
    description: "Define exact amount for each period manually",
    fields: [],
  },
  {
    id: "AUCTION",
    label: "Auction",
    description: "Members bid for the pot each period",
    fields: [
      { label: "Regular Installment", key: "installment_amount", type: "currency" as const },
      { label: "Commission %", key: "commission_pct", type: "percentage" as const },
    ],
  },
];

export default function NewPlanPage() {
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  // Basic info
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [frequency, setFrequency] = useState("MONTHLY");
  const [totalValue, setTotalValue] = useState("");
  const [memberCount, setMemberCount] = useState("");
  const [duration, setDuration] = useState("");

  // Calculation method
  const [calcMethod, setCalcMethod] = useState("FIXED");

  // Dynamic fields for the selected method
  const [fields, setFields] = useState<Record<string, string>>({});

  // Custom schedule (for CUSTOM method)
  const [customSchedule, setCustomSchedule] = useState<CustomScheduleRow[]>([]);

  // Extra custom fields (admin can add their own)
  const [extraFields, setExtraFields] = useState<PlanField[]>([]);

  const handleCalcMethodChange = (method: string) => {
    setCalcMethod(method);
    // Initialize fields for the selected method
    const methodDef = CALC_METHODS.find((m) => m.id === method);
    const initial: Record<string, string> = {};
    methodDef?.fields.forEach((f) => {
      initial[f.key] = "";
    });
    setFields(initial);

    // Initialize custom schedule if needed
    if (method === "CUSTOM" && duration) {
      initCustomSchedule(parseInt(duration));
    }
  };

  const initCustomSchedule = (d: number) => {
    const schedule: CustomScheduleRow[] = [];
    for (let i = 1; i <= d; i++) {
      const existing = customSchedule.find((s) => s.period === i);
      schedule.push({ period: i, amount: existing?.amount || "" });
    }
    setCustomSchedule(schedule);
  };

  const addExtraField = () => {
    setExtraFields([
      ...extraFields,
      {
        id: Date.now().toString(),
        label: "",
        value: "",
        type: "currency",
      },
    ]);
  };

  const updateExtraField = (id: string, updates: Partial<PlanField>) => {
    setExtraFields(extraFields.map((f) => (f.id === id ? { ...f, ...updates } : f)));
  };

  const removeExtraField = (id: string) => {
    setExtraFields(extraFields.filter((f) => f.id !== id));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);

    // Build contribution rules from fields
    let contributionRules: Record<string, unknown>;
    let payoutRules: Record<string, unknown>;

    switch (calcMethod) {
      case "LIFT_BASED":
        contributionRules = {
          type: "LIFT_BASED",
          pre_lift_amount: parseFloat(fields.pre_lift_amount || "0"),
          post_lift_amount: parseFloat(fields.post_lift_amount || "0"),
        };
        break;
      case "CUSTOM":
        contributionRules = {
          type: "CUSTOM",
          schedule: customSchedule
            .filter((s) => s.amount)
            .map((s) => ({ period: s.period, amount: parseFloat(s.amount) })),
          repeat_last_for_remaining: true,
        };
        break;
      case "AUCTION":
        contributionRules = {
          type: "FIXED",
          installment_amount: parseFloat(fields.installment_amount || "0"),
          partial_payments_allowed: true,
        };
        break;
      default:
        contributionRules = {
          type: "FIXED",
          installment_amount: parseFloat(fields.installment_amount || "0"),
          partial_payments_allowed: true,
        };
    }

    // Add extra custom fields to the rules
    const customFields: Record<string, unknown> = {};
    extraFields.forEach((f) => {
      if (f.label && f.value) {
        customFields[f.label] = f.value;
      }
    });
    if (Object.keys(customFields).length > 0) {
      contributionRules.custom_fields = customFields;
    }

    // Payout rules
    if (calcMethod === "AUCTION") {
      payoutRules = {
        type: "AUCTION",
        reserve_price_percentage: 80,
        commission_percentage: parseFloat(fields.commission_pct || "2"),
        highest_bidder_wins: true,
      };
    } else {
      payoutRules = {
        type: "SCHEDULED",
        payout_order: "MEMBER_NUMBER",
        commission_percentage: 0,
        commission_fixed: 0,
      };
    }

    try {
      await chittiApi.createPlan({
        name,
        description: description || null,
        chitti_type: calcMethod,
        total_value: parseFloat(totalValue),
        currency: "INR",
        member_count: parseInt(memberCount),
        frequency,
        duration: parseInt(duration),
        contribution_rules: contributionRules,
        payout_rules: payoutRules,
        fee_rules: {},
        penalty_rules: {},
      });
      router.push("/chitti/plans");
    } catch (e) {
      console.error(e);
    } finally {
      setCreating(false);
    }
  };

  const selectedMethod = CALC_METHODS.find((m) => m.id === calcMethod);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Create Chitti Plan</h2>
          <p className="text-sm text-gray-500">
            Define your own plan — every chitti is unique
          </p>
        </div>

        <div className="card max-w-3xl">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* ===== BASIC INFO ===== */}
            <div className="space-y-4">
              <h3 className="font-semibold text-gray-800 border-b pb-2">Basic Information</h3>

              <div>
                <label className="mb-1 block text-sm font-medium">Plan Name *</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input-field"
                  placeholder="e.g., NAVEEN_NTR_NAGAR_PLAN"
                  required
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="input-field"
                  rows={3}
                  placeholder="Describe your chitti plan in your own words..."
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">Frequency *</label>
                  <select value={frequency} onChange={(e) => setFrequency(e.target.value)} className="input-field">
                    <option value="DAILY">Daily</option>
                    <option value="WEEKLY">Weekly</option>
                    <option value="BIWEEKLY">Bi-weekly</option>
                    <option value="MONTHLY">Monthly</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Duration (periods) *</label>
                  <input
                    type="number"
                    value={duration}
                    onChange={(e) => {
                      setDuration(e.target.value);
                      if (calcMethod === "CUSTOM") initCustomSchedule(parseInt(e.target.value));
                    }}
                    className="input-field"
                    placeholder="25"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">Total Value (₹) *</label>
                  <input
                    type="number"
                    value={totalValue}
                    onChange={(e) => setTotalValue(e.target.value)}
                    className="input-field"
                    placeholder="500000"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Members *</label>
                  <input
                    type="number"
                    value={memberCount}
                    onChange={(e) => setMemberCount(e.target.value)}
                    className="input-field"
                    placeholder="25"
                    required
                  />
                </div>
              </div>
            </div>

            {/* ===== CALCULATION METHOD ===== */}
            <div className="space-y-4">
              <h3 className="font-semibold text-gray-800 border-b pb-2">How Should Installments Work?</h3>
              <p className="text-sm text-gray-500">
                Choose the calculation method that matches your chitti. You can add custom fields below.
              </p>

              <div className="grid grid-cols-2 gap-3">
                {CALC_METHODS.map((method) => (
                  <button
                    key={method.id}
                    type="button"
                    onClick={() => handleCalcMethodChange(method.id)}
                    className={`rounded-lg border-2 p-4 text-left transition-colors ${
                      calcMethod === method.id
                        ? "border-primary-500 bg-primary-50"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <p className="font-medium text-gray-900">{method.label}</p>
                    <p className="text-xs text-gray-500 mt-1">{method.description}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* ===== DYNAMIC FIELDS ===== */}
            {selectedMethod && selectedMethod.fields.length > 0 && (
              <div className="space-y-4">
                <h3 className="font-semibold text-gray-800 border-b pb-2">
                  {selectedMethod.label} — Fields
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  {selectedMethod.fields.map((fieldDef) => (
                    <div key={fieldDef.key}>
                      <label className="mb-1 block text-sm font-medium">{fieldDef.label} *</label>
                      <input
                        type="number"
                        value={fields[fieldDef.key] || ""}
                        onChange={(e) => setFields({ ...fields, [fieldDef.key]: e.target.value })}
                        className="input-field"
                        placeholder={`Enter ${fieldDef.label.toLowerCase()}`}
                        required
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ===== CUSTOM SCHEDULE ===== */}
            {calcMethod === "CUSTOM" && (
              <div className="space-y-4">
                <h3 className="font-semibold text-gray-800 border-b pb-2">
                  Custom Schedule — Define Each Period
                </h3>
                {customSchedule.length > 0 ? (
                  <div className="max-h-64 overflow-y-auto space-y-2">
                    {customSchedule.map((row, idx) => (
                      <div key={row.period} className="flex items-center gap-3">
                        <span className="w-24 text-sm font-medium text-gray-700">
                          Period {row.period}
                        </span>
                        <input
                          type="number"
                          value={row.amount}
                          onChange={(e) => {
                            const newSchedule = [...customSchedule];
                            newSchedule[idx] = { ...newSchedule[idx], amount: e.target.value };
                            setCustomSchedule(newSchedule);
                          }}
                          className="input-field flex-1"
                          placeholder={`Amount for period ${row.period}`}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">Set the Duration above first.</p>
                )}
                {customSchedule.length > 0 && customSchedule.some((s) => s.amount) && (
                  <div className="rounded-lg bg-gray-50 p-3 text-sm">
                    <p className="font-medium text-gray-700">Summary:</p>
                    <p className="text-gray-600">
                      Total per member: ₹
                      {customSchedule
                        .reduce((sum, s) => sum + (parseFloat(s.amount) || 0), 0)
                        .toLocaleString("en-IN")}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* ===== EXTRA CUSTOM FIELDS ===== */}
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b pb-2">
                <h3 className="font-semibold text-gray-800">Additional Fields (Optional)</h3>
                <button type="button" onClick={addExtraField} className="text-sm text-primary-600 hover:underline">
                  + Add Field
                </button>
              </div>
              <p className="text-sm text-gray-500">
                Add any extra fields specific to your chitti — fees, penalties, grace periods, bonus amounts, etc.
              </p>

              {extraFields.length > 0 && (
                <div className="space-y-3">
                  {extraFields.map((field) => (
                    <div key={field.id} className="flex items-center gap-3">
                      <input
                        type="text"
                        value={field.label}
                        onChange={(e) => updateExtraField(field.id, { label: e.target.value })}
                        className="input-field w-40"
                        placeholder="Field name"
                      />
                      <select
                        value={field.type}
                        onChange={(e) => updateExtraField(field.id, { type: e.target.value as PlanField["type"] })}
                        className="input-field w-32"
                      >
                        <option value="currency">Currency (₹)</option>
                        <option value="percentage">Percentage (%)</option>
                        <option value="number">Number</option>
                        <option value="text">Text</option>
                      </select>
                      <input
                        type={field.type === "text" ? "text" : "number"}
                        value={field.value}
                        onChange={(e) => updateExtraField(field.id, { value: e.target.value })}
                        className="input-field flex-1"
                        placeholder="Value"
                      />
                      <button
                        type="button"
                        onClick={() => removeExtraField(field.id)}
                        className="text-red-500 hover:text-red-700 text-sm"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {extraFields.length === 0 && (
                <div className="rounded-lg border border-dashed border-gray-300 p-4 text-center text-sm text-gray-500">
                  No extra fields added. Click "+ Add Field" to add custom fields for your plan.
                </div>
              )}
            </div>

            {/* ===== PREVIEW ===== */}
            {name && totalValue && memberCount && duration && (
              <div className="rounded-lg bg-gray-50 p-4 space-y-2">
                <h3 className="font-semibold text-gray-800">Plan Summary</h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <p><span className="text-gray-500">Name:</span> {name}</p>
                  <p><span className="text-gray-500">Method:</span> {selectedMethod?.label}</p>
                  <p><span className="text-gray-500">Total Value:</span> ₹{parseFloat(totalValue).toLocaleString("en-IN")}</p>
                  <p><span className="text-gray-500">Members:</span> {memberCount}</p>
                  <p><span className="text-gray-500">Duration:</span> {duration} {frequency.toLowerCase()} periods</p>
                  <p><span className="text-gray-500">Per Member / Period:</span> ₹{(parseFloat(totalValue) / parseInt(memberCount)).toLocaleString("en-IN")}</p>
                </div>
                {Object.keys(fields).length > 0 && (
                  <div className="mt-2 text-sm">
                    <p className="font-medium text-gray-700">Configured Fields:</p>
                    {Object.entries(fields).map(([key, val]) => (
                      <p key={key} className="text-gray-600">
                        {selectedMethod?.fields.find((f) => f.key === key)?.label || key}: {val ? `₹${val}` : "(not set)"}
                      </p>
                    ))}
                  </div>
                )}
                {extraFields.length > 0 && (
                  <div className="mt-2 text-sm">
                    <p className="font-medium text-gray-700">Custom Fields:</p>
                    {extraFields.filter((f) => f.label).map((f) => (
                      <p key={f.id} className="text-gray-600">
                        {f.label}: {f.value || "(not set)"}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button type="button" onClick={() => router.back()} className="btn-secondary">
                Cancel
              </button>
              <button type="submit" disabled={creating} className="btn-primary">
                {creating ? "Creating..." : "Create Plan"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </DashboardLayout>
  );
}
