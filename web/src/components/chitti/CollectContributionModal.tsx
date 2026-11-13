"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, IndianRupee, X } from "lucide-react";
import { chittiApi, type ChittiContribution } from "@/services/chitti";
import { getApiErrorMessage } from "@/services/api-client";
import { formatCurrency } from "@/lib/utils";

/**
 * One collection flow for the whole Chitti module.
 *
 * Chitti money is independent of any finance account: a contribution is always
 * recorded against the member's period row, never against a loan. The dialog
 * pre-selects the first unpaid period and its outstanding amount so the common
 * case (collect what is due) is two clicks: open, confirm.
 */
export default function CollectContributionModal({
  chittiId,
  member,
  onClose,
  onSaved,
  presetPeriod,
}: {
  chittiId: string;
  member: { id: string; name: string; number?: number | null };
  onClose: () => void;
  onSaved: (message: string) => void | Promise<void>;
  presetPeriod?: number;
}) {
  const [rows, setRows] = useState<ChittiContribution[] | null>(null);
  const [period, setPeriod] = useState<number | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("CASH");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // One key per dialog: a retry can never double-count the same money.
  const idempotencyKey = useRef<string>(
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `chitti-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );

  const open = (rows ?? []).filter((r) => Number(r.remaining_amount) > 0);
  const selected = open.find((r) => r.period_number === period) ?? null;

  const load = useCallback(async () => {
    try {
      const data = await chittiApi.getMemberContributions(chittiId, member.id);
      setRows(data);
      const wanted =
        (presetPeriod != null && data.find((r) => r.period_number === presetPeriod && Number(r.remaining_amount) > 0)) ||
        data.find((r) => Number(r.remaining_amount) > 0);
      if (wanted) {
        setPeriod(wanted.period_number);
        setAmount(String(wanted.remaining_amount));
      }
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not load this member's contributions."));
    }
  }, [chittiId, member.id, presetPeriod]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (saving || !selected) return;
    const value = Number(amount);
    const remaining = Number(selected.remaining_amount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter an amount greater than zero.");
      return;
    }
    if (value > remaining + 0.005) {
      setError(`Only ${formatCurrency(remaining)} is left to collect for this period.`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await chittiApi.recordContribution(chittiId, {
        member_id: member.id,
        period_number: selected.period_number,
        amount: value,
        payment_method: method,
        payment_date: new Date().toISOString().slice(0, 10),
        reference_number: reference.trim() || undefined,
        notes: notes.trim() || undefined,
        idempotency_key: idempotencyKey.current,
      });
      await onSaved(
        `${formatCurrency(value)} collected from ${member.name} (period ${selected.period_number}).`
      );
    } catch (e: unknown) {
      setError(getApiErrorMessage(e, "Could not record this contribution."));
    } finally {
      setSaving(false);
    }
  };

  const previewChange =
    selected && Number(amount) > 0
      ? Math.max(Number(selected.remaining_amount) - Number(amount), 0)
      : null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-surface-100 px-4 py-4 sm:px-6">
          <div className="min-w-0">
            <h3 className="text-lg font-bold text-surface-900">Collect contribution</h3>
            <p className="text-xs text-surface-500">
              {member.name}
              {member.number ? ` • Member #${member.number}` : ""} • cash, UPI or bank
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-surface-400 hover:bg-surface-100 transition-colors"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 p-4 pb-0 sm:p-6 sm:pb-0">
          {rows === null ? (
            <p className="text-sm text-surface-500">Loading what this member owes…</p>
          ) : open.length === 0 ? (
            <div className="flex items-center gap-3 rounded-xl bg-success-50 p-4 text-sm text-success-700">
              <CheckCircle2 size={18} />
              Every period for this member is fully paid.
            </div>
          ) : (
            <>
              <div>
                <label className="label">Which period?</label>
                <select
                  className="input-field"
                  value={period ?? ""}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    setPeriod(next);
                    const row = open.find((r) => r.period_number === next);
                    if (row) setAmount(String(row.remaining_amount));
                    setError(null);
                  }}
                >
                  {open.map((r) => (
                    <option key={r.id} value={r.period_number}>
                      Period {r.period_number} — {formatCurrency(r.remaining_amount)} due
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Amount received</label>
                <div className="relative">
                  <IndianRupee
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
                  />
                  <input
                    className="input-field pl-9"
                    type="number"
                    min="0"
                    step="0.01"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                  />
                </div>
                {selected && (
                  <p className="mt-1 text-xs text-surface-500">
                    Period {selected.period_number}: expected{" "}
                    {formatCurrency(selected.expected_amount)}, already paid{" "}
                    {formatCurrency(selected.paid_amount)}
                    {previewChange !== null && ` → ${formatCurrency(previewChange)} will remain`}
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="label">Paid by</label>
                  <select
                    className="input-field"
                    value={method}
                    onChange={(e) => setMethod(e.target.value)}
                  >
                    <option value="CASH">Cash</option>
                    <option value="UPI">UPI</option>
                    <option value="BANK_TRANSFER">Bank transfer</option>
                    <option value="OTHER">Other</option>
                  </select>
                </div>
                <div>
                  <label className="label">Reference (optional)</label>
                  <input
                    className="input-field"
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                    placeholder="UPI / receipt no."
                  />
                </div>
              </div>

              <div>
                <label className="label">Note (optional)</label>
                <input
                  className="input-field"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Anything to remember about this payment"
                />
              </div>
            </>
          )}

          {error && (
            <p className="rounded-xl bg-danger-50 px-3 py-2 text-sm text-danger-700">{error}</p>
          )}

          {/* Actions stay reachable on a phone without hunting for them. */}
          <div className="sticky bottom-0 -mx-4 mt-1 flex flex-col-reverse gap-2 border-t border-surface-100 bg-white px-4 py-3 sm:-mx-6 sm:flex-row sm:justify-end sm:px-6">
            <button
              onClick={onClose}
              className="btn-secondary w-full sm:w-auto"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              onClick={submit}
              className="btn-primary w-full sm:w-auto"
              disabled={saving || !selected || open.length === 0}
            >
              {saving ? "Recording…" : "Confirm collection"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
