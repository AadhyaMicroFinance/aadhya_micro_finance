"use client";

import { useCallback, useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { getApiErrorMessage } from "@/services/api-client";
import { adminApi } from "@/services/admin";
import type { WhatsAppStatus } from "@/types";
import {
  AlertCircle,
  CheckCircle2,
  MessageCircle,
  RefreshCw,
  Send,
  XCircle,
} from "lucide-react";

const TEMPLATES = [
  "Payment Received",
  "Payment Due Reminder",
  "Payment Overdue",
  "Welcome Message",
];

function maskPhone(value: string): string {
  if (value.length <= 4) return "••••";
  return `${value.slice(0, 2)}${"•".repeat(Math.max(2, value.length - 6))}${value.slice(-4)}`;
}

export default function WhatsAppPage() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setStatus(await adminApi.whatsapp());
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to load WhatsApp status."));
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
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">WhatsApp Integration</h1>
            <p className="mt-1 text-sm text-surface-500">
              Delivery status and real message log
            </p>
          </div>
          <button type="button" onClick={() => void load()} disabled={loading} className="btn-secondary btn-sm">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {error && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
            <AlertCircle size={17} />
            <span className="flex-1">{error}</span>
            <button type="button" onClick={() => void load()} className="btn-secondary btn-sm">Retry</button>
          </div>
        )}

        {loading ? (
          <TableSkeleton rows={4} cols={3} />
        ) : status ? (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="card flex items-center gap-4">
                <div className="rounded-xl bg-success-50 p-3 text-success-600"><Send size={20} /></div>
                <div>
                  <p className="text-xs font-medium text-surface-500 uppercase">Sent Today</p>
                  <p className="text-2xl font-bold text-surface-900">{status.stats.sent_today}</p>
                </div>
              </div>
              <div className="card flex items-center gap-4">
                <div className="rounded-xl bg-brand-50 p-3 text-brand-600"><CheckCircle2 size={20} /></div>
                <div>
                  <p className="text-xs font-medium text-surface-500 uppercase">Delivery Rate</p>
                  <p className="text-2xl font-bold text-surface-900">
                    {status.stats.delivery_rate === null ? "—" : `${status.stats.delivery_rate}%`}
                  </p>
                </div>
              </div>
              <div className="card flex items-center gap-4">
                <div className="rounded-xl bg-danger-50 p-3 text-danger-600"><XCircle size={20} /></div>
                <div>
                  <p className="text-xs font-medium text-surface-500 uppercase">Failed Today</p>
                  <p className="text-2xl font-bold text-surface-900">{status.stats.failed_today}</p>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="flex flex-wrap items-center gap-3 mb-4">
                <div className="rounded-xl bg-success-50 p-2.5 text-success-600"><MessageCircle size={18} /></div>
                <h3 className="text-sm font-semibold text-surface-900">Connection</h3>
                <span className={status.configured ? "badge-success ml-auto" : "badge-neutral ml-auto"}>
                  {status.configured ? "Configured" : "Not configured"}
                </span>
              </div>
              <p className="text-xs leading-relaxed text-surface-500">
                {status.configured
                  ? "Credentials are loaded from the backend environment. Values are never shown here."
                  : "Set the WhatsApp credentials in the backend environment to enable delivery. Existing message records remain visible below."}
              </p>
              <div className="mt-5 space-y-2">
                {TEMPLATES.map((template) => (
                  <div
                    key={template}
                    className="flex items-center justify-between rounded-xl border border-surface-100 p-4"
                  >
                    <span className="text-sm font-medium text-surface-900">{template}</span>
                    <span className="text-xs text-surface-400">Template name</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600"><MessageCircle size={18} /></div>
                <h3 className="text-sm font-semibold text-surface-900">Recent Messages</h3>
              </div>
              {status.messages.length === 0 ? (
                <EmptyState
                  icon="📱"
                  title="No messages yet"
                  description="Delivery records will appear here when notifications are sent."
                />
              ) : (
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Customer</th>
                        <th>Phone</th>
                        <th>Template</th>
                        <th>Status</th>
                        <th>Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {status.messages.map((message) => (
                        <tr key={message.id}>
                          <td className="whitespace-nowrap text-xs text-surface-500">
                            {new Date(message.created_at).toLocaleString()}
                          </td>
                          <td className="font-medium">{message.customer_name}</td>
                          <td className="font-mono text-xs">{maskPhone(message.phone_number)}</td>
                          <td>{message.template_name}</td>
                          <td>
                            <span className={message.status === "FAILED" ? "badge-danger" : "badge-neutral"}>
                              {message.status}
                            </span>
                          </td>
                          <td className="max-w-xs truncate text-xs text-surface-500" title={message.error_message ?? ""}>
                            {message.error_message ?? "—"}
                          </td>
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
