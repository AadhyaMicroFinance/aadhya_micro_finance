"use client";

import { useCallback, useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { getApiErrorMessage } from "@/services/api-client";
import { adminApi } from "@/services/admin";
import type { EffectiveSettings } from "@/types";
import { AlertCircle, Bell, CheckCircle2, CreditCard, RefreshCw, Settings, ShieldCheck } from "lucide-react";

export default function SettingsPage() {
  const [settings, setSettings] = useState<EffectiveSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSettings(await adminApi.settings());
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to load settings."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-surface-500">
            Effective system configuration and approved operating rules
          </p>
        </div>

        {error && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
            <AlertCircle size={17} />
            <span className="flex-1">{error}</span>
            <button type="button" onClick={() => void load()} className="btn-secondary btn-sm">
              <RefreshCw size={14} /> Retry
            </button>
          </div>
        )}

        {loading ? (
          <TableSkeleton rows={3} cols={2} />
        ) : settings ? (
          <>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="card">
                <div className="flex items-center gap-3 mb-5">
                  <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600"><Settings size={18} /></div>
                  <h3 className="text-sm font-semibold text-surface-900">Application</h3>
                </div>
                <dl className="space-y-4 text-sm">
                  <div className="flex items-start justify-between gap-4">
                    <dt className="text-surface-500">Business timezone</dt>
                    <dd className="font-medium text-surface-900">{settings.business_timezone}</dd>
                  </div>
                  <div className="flex items-start justify-between gap-4">
                    <dt className="text-surface-500">WhatsApp integration</dt>
                    <dd className={settings.whatsapp_configured ? "badge-success" : "badge-neutral"}>
                      {settings.whatsapp_configured ? "Configured" : "Not configured"}
                    </dd>
                  </div>
                </dl>
              </div>

              <div className="card">
                <div className="flex items-center gap-3 mb-5">
                  <div className="rounded-xl bg-success-50 p-2.5 text-success-600"><ShieldCheck size={18} /></div>
                  <h3 className="text-sm font-semibold text-surface-900">Approved financial rules</h3>
                </div>
                <div className="flex gap-3 rounded-xl border border-success-100 bg-success-50/50 p-4">
                  <CheckCircle2 size={18} className="mt-0.5 flex-shrink-0 text-success-600" />
                  <div>
                    <p className="text-sm font-medium text-surface-900">Credits are applied explicitly</p>
                    <p className="mt-1 text-xs leading-relaxed text-surface-500">
                      Excess cash, available credit and allocated contributions stay separate. This rule is
                      enforced by the backend and is not an operator preference.
                    </p>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="flex items-center gap-3 mb-5">
                  <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600"><CreditCard size={18} /></div>
                  <h3 className="text-sm font-semibold text-surface-900">Payment handling</h3>
                </div>
                <dl className="space-y-4 text-sm">
                  <div className="flex items-start justify-between gap-4">
                    <dt className="text-surface-500">Advance payment policy</dt>
                    <dd className="font-medium text-surface-900">Explicit credit use only</dd>
                  </div>
                  <div className="flex items-start justify-between gap-4">
                    <dt className="text-surface-500">Revenue recognition</dt>
                    <dd className="font-medium text-surface-900">Allocated contributions only</dd>
                  </div>
                </dl>
              </div>

              <div className="card">
                <div className="flex items-center gap-3 mb-5">
                  <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600"><Bell size={18} /></div>
                  <h3 className="text-sm font-semibold text-surface-900">Notification delivery</h3>
                </div>
                <p className="text-sm font-medium text-surface-900">
                  {settings.notification_delivery_enabled ? "Enabled" : "Not enabled"}
                </p>
                <p className="mt-2 text-xs leading-relaxed text-surface-500">
                  Delivery preferences are not shown as active controls because automated reminders are not
                  enabled in this deployment. The WhatsApp screen reports the real delivery log when available.
                </p>
              </div>
            </div>

            <div className="card">
              <div className="flex items-center gap-3 mb-5">
                <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600"><Settings size={18} /></div>
                <h3 className="text-sm font-semibold text-surface-900">Stored setting values</h3>
              </div>
              {settings.saved_settings.length === 0 ? (
                <EmptyState
                  icon="⚙️"
                  title="No saved overrides"
                  description="The application is using its built-in approved configuration."
                />
              ) : (
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Key</th>
                        <th>Value</th>
                        <th>Description</th>
                        <th>Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {settings.saved_settings.map((row) => (
                        <tr key={row.key}>
                          <td className="font-mono text-xs">{row.key}</td>
                          <td className="font-mono text-xs">{JSON.stringify(row.value)}</td>
                          <td>{row.description ?? "—"}</td>
                          <td>{row.updated_at ? new Date(row.updated_at).toLocaleString() : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        ) : null}
      </div>
    </DashboardLayout>
  );
}
