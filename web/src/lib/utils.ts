import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

/**
 * Coerce an API value to a finite number.
 *
 * Financial dashboards must never print ₹NaN. Invalid values are reported to
 * the console (so a real calculation bug is not silently hidden) and rendered
 * as 0.
 */
export function toNumber(value: unknown, field?: string): number {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      console.error(`[finance] non-finite value${field ? ` in ${field}` : ""}:`, value);
      return 0;
    }
    return value;
  }
  if (value === null || value === undefined || value === "") return 0;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    console.error(`[finance] unparseable numeric value${field ? ` in ${field}` : ""}:`, value);
    return 0;
  }
  return parsed;
}

export function formatCurrency(amount: unknown, field?: string): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(toNumber(amount, field));
}

export function formatDate(dateStr: string): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(dateStr: string): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function getInitials(name: string): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    // Active/Success
    ACTIVE: "badge-success",
    COMPLETED: "badge-success",
    PAID: "badge-success",
    DELIVERED: "badge-success",
    CONFIRMED: "badge-success",
    APPROVED: "badge-success",
    READ: "badge-success",
    GENERATED: "badge-success",
    
    // Warning/Pending
    PENDING: "badge-warning",
    DUE: "badge-warning",
    UPCOMING: "badge-warning",
    DRAFT: "badge-warning",
    PENDING_AGREEMENT: "badge-warning",
    AGREEMENT_GENERATED: "badge-warning",
    AGREEMENT_PRINTED: "badge-warning",
    QUEUED: "badge-warning",
    SENT: "badge-warning",
    PARTIALLY_PAID: "badge-info",
    
    // Danger
    OVERDUE: "badge-danger",
    FAILED: "badge-danger",
    CANCELLED: "badge-danger",
    BLOCKED: "badge-danger",
    DEFAULTED: "badge-danger",
    REVERSED: "badge-danger",
    REJECTED: "badge-danger",
    
    // Neutral
    INACTIVE: "badge-neutral",
    CLOSED: "badge-neutral",
    LEFT: "badge-neutral",
    ARCHIVED: "badge-neutral",
    
    // Brand/Info
    RUNNING: "badge-brand",
    PAUSED: "badge-info",
    REPLACED: "badge-warning",
  };
  return colors[status] || "badge-neutral";
}

export function getStatusDot(status: string): string {
  const dots: Record<string, string> = {
    ACTIVE: "status-dot-success",
    RUNNING: "status-dot-info",
    COMPLETED: "status-dot-success",
    PAID: "status-dot-success",
    CONFIRMED: "status-dot-success",
    PENDING: "status-dot-warning",
    UPCOMING: "status-dot-warning",
    DRAFT: "status-dot-warning",
    OVERDUE: "status-dot-danger",
    FAILED: "status-dot-danger",
    CANCELLED: "status-dot-danger",
    BLOCKED: "status-dot-danger",
    PAUSED: "status-dot-info",
    INACTIVE: "status-dot-neutral",
  };
  return dots[status] || "status-dot-neutral";
}
