"use client";

import { useCallback, useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { getApiErrorMessage } from "@/services/api-client";
import { adminApi } from "@/services/admin";
import type { AuditLogEntry } from "@/types";
import {
  AlertCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Search,
  Shield,
} from "lucide-react";

const ACTIONS = [
  "CUSTOMER_CREATED",
  "FINANCE_CREATED",
  "PAYMENT_CREATED",
  "PAYMENT_REVERSED",
  "USER_CREATED",
  "SETTINGS_CHANGED",
];

function formatValue(value: Record<string, unknown> | null): string {
  if (!value || Object.keys(value).length === 0) return "—";
  return JSON.stringify(value);
}

export default function AuditPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [observedActions, setObservedActions] = useState<string[]>([]);

  const load = useCallback(async () => {
    // `reloadKey` is a deliberate refresh trigger for the Apply/Reset buttons.
    void reloadKey;
    setLoading(true);
    setError("");
    try {
      const response = await adminApi.audit({
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        action: action || undefined,
        entity_type: entityType || undefined,
        page,
        per_page: 25,
      });
      const loaded = response.data ?? [];
      setEntries(loaded);
      // Keep every action seen in this session selectable, even when a filter
      // currently hides its rows; the backend has many more than the defaults.
      const seen = loaded.map((entry) => entry.action).filter(Boolean);
      if (seen.length) {
        setObservedActions((current) =>
          Array.from(new Set([...current, ...seen])).sort()
        );
      }
      setTotal(response.meta?.total ?? 0);
      setTotalPages(response.meta?.total_pages ?? 0);
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to load audit logs."));
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [action, dateFrom, dateTo, entityType, page, reloadKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const apply = () => {
    setPage(1);
    setReloadKey((value) => value + 1);
  };
  const reset = () => {
    setDateFrom("");
    setDateTo("");
    setAction("");
    setEntityType("");
    setPage(1);
    setReloadKey((value) => value + 1);
  };

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Audit Logs</h1>
          <p className="mt-1 text-sm text-surface-500">Track system mutations and user actions</p>
        </div>

        <div className="card">
          <div className="flex items-center gap-3 mb-6">
            <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600"><Shield size={18} /></div>
            <h3 className="text-sm font-semibold text-surface-900">Activity Log</h3>
            {!loading && <span className="badge-neutral ml-auto">{total} entries</span>}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <div>
              <label className="input-label" htmlFor="audit-from">From</label>
              <input
                id="audit-from"
                type="date"
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
                className="input-field"
              />
            </div>
            <div>
              <label className="input-label" htmlFor="audit-to">To</label>
              <input
                id="audit-to"
                type="date"
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
                className="input-field"
              />
            </div>
            <div>
              <label className="input-label" htmlFor="audit-action">Action</label>
              <select
                id="audit-action"
                value={action}
                onChange={(event) => setAction(event.target.value)}
                className="input-field"
              >
                <option value="">All actions</option>
                {Array.from(new Set([...ACTIONS, ...observedActions])).map((item) => (
                  <option key={item} value={item}>{item.replaceAll("_", " ")}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="input-label" htmlFor="audit-entity">Entity type</label>
              <input
                id="audit-entity"
                type="text"
                value={entityType}
                onChange={(event) => setEntityType(event.target.value)}
                placeholder="e.g. customer"
                className="input-field"
              />
            </div>
            <div className="flex items-end gap-2">
              <button type="button" onClick={apply} disabled={loading} className="btn-primary flex-1">
                <Search size={15} /> Apply
              </button>
              <button type="button" onClick={reset} disabled={loading} className="btn-secondary" aria-label="Reset filters">
                <RotateCcw size={15} />
              </button>
            </div>
          </div>

          {error && (
            <div className="mt-5 flex items-center gap-2 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
              <AlertCircle size={16} /> {error}
            </div>
          )}

          <div className="mt-6">
            {loading ? (
              <TableSkeleton rows={6} cols={5} />
            ) : entries.length === 0 ? (
              <EmptyState
                icon="📝"
                title="No audit entries found"
                description="Try widening the date range or clearing a filter."
                action={<button type="button" onClick={reset} className="btn-secondary">Clear filters</button>}
              />
            ) : (
              <>
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Actor</th>
                        <th>Action</th>
                        <th>Entity</th>
                        <th aria-label="Details" />
                      </tr>
                    </thead>
                    <tbody>
                      {entries.map((entry) => (
                        <AuditRow
                          key={entry.id}
                          entry={entry}
                          expanded={expanded === entry.id}
                          onToggle={() => setExpanded((current) => current === entry.id ? null : entry.id)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-xs text-surface-500">
                    Page {page} of {Math.max(totalPages, 1)} · {total} entries
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setPage((value) => Math.max(1, value - 1))}
                      disabled={page <= 1}
                      className="btn-secondary btn-sm"
                    >
                      <ChevronLeft size={14} /> Previous
                    </button>
                    <button
                      type="button"
                      onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                      disabled={page >= totalPages}
                      className="btn-secondary btn-sm"
                    >
                      Next <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}

function AuditRow({
  entry,
  expanded,
  onToggle,
}: {
  entry: AuditLogEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="cursor-pointer" onClick={onToggle}>
        <td className="whitespace-nowrap text-xs text-surface-500">
          {new Date(entry.created_at).toLocaleString()}
        </td>
        <td className="font-medium">{entry.actor}</td>
        <td><span className="badge-neutral">{entry.action}</span></td>
        <td>
          <span className="text-xs text-surface-600">{entry.entity_type}</span>
          {entry.entity_id && (
            <span className="ml-1 font-mono text-[10px] text-surface-400">
              {entry.entity_id.slice(0, 8)}
            </span>
          )}
        </td>
        <td className="text-right">
          <ChevronDown
            size={16}
            className={`ml-auto transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={5} className="bg-surface-50">
            <div className="grid grid-cols-1 gap-3 py-2 text-xs md:grid-cols-2">
              <div>
                <p className="font-semibold text-surface-500">Previous value</p>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all font-mono text-[11px] text-surface-700">
                  {formatValue(entry.previous_value)}
                </pre>
              </div>
              <div>
                <p className="font-semibold text-surface-500">New value</p>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all font-mono text-[11px] text-surface-700">
                  {formatValue(entry.new_value)}
                </pre>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
