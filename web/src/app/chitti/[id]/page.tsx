"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  chittiApi,
  type ChittiInstance,
  type ChittiSummary,
  type ChittiMember,
  type ChittiPeriodSchedule,
  type ChittiPayout,
  type Agreement,
  type ActivationStatus,
} from "@/services/chitti";
import type { Customer } from "@/types";
import apiClient, { getApiErrorMessage, getApiErrorDetails } from "@/services/api-client";
import type { ApiResponse } from "@/types";
import { formatCurrency, formatDate, cn, getStatusColor, getInitials } from "@/lib/utils";
import ProgressBar from "@/components/ui/ProgressBar";
import Avatar from "@/components/ui/Avatar";
import EmptyState from "@/components/ui/EmptyState";
import { PageSkeleton } from "@/components/ui/Skeleton";
import {
  ArrowLeft,
  Plus,
  Play,
  Pause,
  CheckCircle2,
  XCircle,
  FileText,
  Printer,
  UserCheck,
  Users,
  Calendar,
  TrendingUp,
  TrendingDown,
  IndianRupee,
  X,
  Search,
  ChevronRight,
} from "lucide-react";

type Tab = "overview" | "members" | "schedule" | "payouts";

// Display-only lifecycle labels mapped onto the existing backend statuses.
const DISPLAY_STATE_LABELS: Record<string, string> = {
  READY_TO_START: "Ready to Start",
  ACTIVATION_BLOCKED: "Activation Blocked",
  ACTIVE: "Active",
  PAUSED: "Paused",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  DRAFT: "Draft",
  UPCOMING: "Upcoming",
  ARCHIVED: "Archived",
};

function displayStateLabel(state?: string | null): string {
  if (!state) return "—";
  return DISPLAY_STATE_LABELS[state] ?? state.replace(/_/g, " ");
}

// ============================================================
// Agreement Preview Modal
// ============================================================
function AgreementPreviewModal({
  agreement,
  chittiName,
  memberName,
  onClose,
  onPrint,
  onConfirm,
}: {
  agreement: Agreement;
  chittiName: string;
  memberName: string;
  onClose: () => void;
  onPrint: () => void;
  onConfirm: () => void;
}) {
  const snapshot = agreement.agreement_snapshot as Record<string, unknown>;
  const customer = snapshot?.customer as Record<string, string> | undefined;
  const chittiSnap = snapshot?.chitti as Record<string, unknown> | undefined;
  const plan = snapshot?.plan as Record<string, unknown> | undefined;
  const contribRules = plan?.contribution_rules as Record<string, unknown> | undefined;

  const handlePrint = () => {
    window.print();
    onPrint();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content max-w-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {/* Print-friendly agreement content */}
        <div id="agreement-content" className="p-8 print:p-4">
          {/* Header */}
          <div className="text-center border-b-2 border-surface-900 pb-4 mb-6">
            <h1 className="text-2xl font-bold tracking-wide text-surface-900">CHITTI AGREEMENT</h1>
            <p className="text-sm text-surface-600 mt-1">Agreement No: {agreement.agreement_number}</p>
            <p className="text-sm text-surface-600">Date: {formatDate(agreement.agreement_date)}</p>
          </div>

          {/* Chitti Details */}
          <Section title="Chitti Details">
            <DetailRow label="Name" value={String(chittiSnap?.name || chittiName)} />
            <DetailRow label="Value" value={formatCurrency(Number(chittiSnap?.total_value || 0))} />
            <DetailRow label="Frequency" value={String(plan?.frequency || "")} />
            <DetailRow label="Duration" value={`${String(plan?.duration || "")} periods`} />
            <DetailRow label="Members" value={String(plan?.member_count || "")} />
            <DetailRow label="Type" value={String(plan?.chitti_type || "")} />
          </Section>

          {/* Member Details */}
          <Section title="Member Details">
            <DetailRow label="Name" value={customer?.full_name || memberName} />
            <DetailRow label="Phone" value={customer?.mobile_number || ""} />
            <DetailRow label="Address" value={`${customer?.address || ""}, ${customer?.city || ""}, ${customer?.state || ""}`} />
            <DetailRow label="Customer ID" value={customer?.customer_code || ""} />
            {customer?.pan_number && <DetailRow label="PAN" value={customer.pan_number} />}
            {customer?.nominee_name && <DetailRow label="Nominee" value={`${customer.nominee_name} (${customer.nominee_relation})`} />}
          </Section>

          {/* Contribution Terms */}
          <Section title="Contribution Terms">
            {contribRules?.type === "FIXED" && (
              <p className="text-sm">Fixed installment of <span className="font-bold">{formatCurrency(Number(contribRules.installment_amount || 0))}</span> per period for <span className="font-bold">{String(plan?.duration)}</span> periods.</p>
            )}
            {contribRules?.type === "LIFT_BASED" && (
              <div className="text-sm space-y-1">
                <p>Before lifting: <span className="font-bold">{formatCurrency(Number(contribRules.pre_lift_amount || 0))}</span> per period</p>
                <p>After lifting: <span className="font-bold">{formatCurrency(Number(contribRules.post_lift_amount || 0))}</span> per period</p>
              </div>
            )}
            {contribRules?.type === "CUSTOM" && (
              <div className="text-sm space-y-1">
                <p>Custom schedule:</p>
                {Array.isArray(contribRules.schedule) && contribRules.schedule.map((s: Record<string, unknown>) => (
                  <p key={String(s.period)}>Period {String(s.period)}: <span className="font-bold">{formatCurrency(Number(s.amount || 0))}</span></p>
                ))}
              </div>
            )}
          </Section>

          {/* Signature Area */}
          <div className="mt-8 pt-4 border-t border-surface-300">
            <div className="flex justify-between text-sm">
              <div className="text-center">
                <div className="border-b border-surface-400 w-40 mb-1">&nbsp;</div>
                <p className="text-surface-500">Member Signature</p>
              </div>
              <div className="text-center">
                <div className="border-b border-surface-400 w-40 mb-1">&nbsp;</div>
                <p className="text-surface-500">Authorized Signatory</p>
              </div>
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 p-6 border-t border-surface-100 print:hidden">
          <button onClick={onClose} className="btn-secondary flex-1">
            Close
          </button>
          <button onClick={handlePrint} className="btn-primary flex-1">
            <Printer size={16} />
            Print Agreement
          </button>
          {agreement.agreement_status === "PRINTED" && (
            <button onClick={onConfirm} className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-success-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-success-700 transition-colors">
              <CheckCircle2 size={16} />
              Confirm Agreement
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h2 className="text-xs font-bold uppercase tracking-wider text-surface-500 mb-3 border-b border-surface-200 pb-2">{title}</h2>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex text-sm">
      <span className="w-32 text-surface-500">{label}:</span>
      <span className="font-medium text-surface-900">{value}</span>
    </div>
  );
}

// ============================================================
// Add Member Modal
// ============================================================
function AddMemberModal({
  chittiId,
  currentCount,
  maxCount,
  enrolledCustomerIds,
  onClose,
  onAdded,
}: {
  chittiId: string;
  currentCount: number;
  maxCount: number;
  enrolledCustomerIds: Set<string>;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [search, setSearch] = useState("");
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState("");

  const searchCustomers = useCallback(async (q: string) => {
    if (q.length < 2) { setCustomers([]); return; }
    setLoading(true);
    try {
      const res = await apiClient.get<ApiResponse<Customer[]>>("/customers", { params: { search: q, per_page: 20 } });
      setCustomers(res.data.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => searchCustomers(search), 300);
    return () => clearTimeout(t);
  }, [search, searchCustomers]);

  const handleAdd = async () => {
    if (!selectedCustomer) return;
    setAdding(true);
    setError("");
    try {
      await chittiApi.addMember(chittiId, {
        customer_id: selectedCustomer.id,
        payout_order: currentCount + 1,
      });
      onAdded();
    } catch (e: unknown) {
      // The API sends a specific 409 (DUPLICATE_ENROLLMENT) message; show it
      // instead of the generic "Request failed with status code 409". The
      // dialog stays open with the selected customer preserved.
      setError(getApiErrorMessage(e, "Failed to add member. Please try again."));
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-bold text-surface-900">Add Member</h2>
            <p className="text-sm text-surface-500">Members: {currentCount} / {maxCount} • Next: #{currentCount + 1}</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-surface-400 hover:bg-surface-100 transition-colors">
            <X size={18} />
          </button>
        </div>

        {currentCount >= maxCount ? (
          <EmptyState icon="👥" title="Chitti is full" description={`Maximum ${maxCount} members reached.`} />
        ) : !selectedCustomer ? (
          <div className="space-y-4">
            <div className="relative">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, phone, or customer code..."
                className="input-field pl-10"
                autoFocus
              />
            </div>
            {loading && <p className="text-sm text-surface-500 text-center py-2">Searching...</p>}
            {customers.length > 0 && (
              <div className="max-h-60 overflow-y-auto rounded-xl border border-surface-100 divide-y divide-surface-50">
                {customers.map((c) => {
                  const alreadyEnrolled = enrolledCustomerIds.has(c.id);
                  return (
                    <button
                      key={c.id}
                      onClick={() => { if (!alreadyEnrolled) setSelectedCustomer(c); }}
                      disabled={alreadyEnrolled}
                      className={cn(
                        "w-full text-left p-4 flex items-center gap-3 transition-colors",
                        alreadyEnrolled ? "cursor-not-allowed opacity-60" : "hover:bg-surface-50"
                      )}
                    >
                      <Avatar name={c.full_name} size="md" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-surface-900 truncate">{c.full_name}</p>
                        <p className="text-xs text-surface-500">{c.customer_code} • {c.mobile_number}</p>
                      </div>
                      {alreadyEnrolled ? (
                        <span className="badge badge-warning">Already enrolled</span>
                      ) : (
                        <ChevronRight size={16} className="text-surface-300" />
                      )}
                    </button>
                  );
                })}
              </div>
            )}
            {!loading && search.length >= 2 && customers.length === 0 && (
              <EmptyState icon="🔍" title="No customers found" description="Try a different search term" />
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-xl bg-surface-50 p-4 flex items-center gap-4">
              <Avatar name={selectedCustomer.full_name} size="lg" />
              <div className="flex-1">
                <p className="font-semibold text-surface-900">{selectedCustomer.full_name}</p>
                <p className="text-sm text-surface-500">{selectedCustomer.customer_code} • {selectedCustomer.mobile_number}</p>
                {selectedCustomer.address && (
                  <p className="text-xs text-surface-400 mt-0.5">{selectedCustomer.address}, {selectedCustomer.city}</p>
                )}
              </div>
              <button onClick={() => setSelectedCustomer(null)} className="text-xs text-brand-600 hover:text-brand-700 font-medium">
                Change
              </button>
            </div>

            {error && (
              <div className="rounded-xl bg-danger-50 border border-danger-100 p-3 text-sm text-danger-700">{error}</div>
            )}

            <div className="flex gap-3">
              <button onClick={onClose} className="btn-secondary flex-1">Cancel</button>
              <button onClick={handleAdd} disabled={adding} className="btn-primary flex-1">
                {adding ? "Adding..." : `Add as Member #${currentCount + 1}`}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Main Page
// ============================================================
export default function ChittiDetailPage() {
  const params = useParams();
  const chittiId = params.id as string;

  const [chitti, setChitti] = useState<ChittiInstance | null>(null);
  const [summary, setSummary] = useState<ChittiSummary | null>(null);
  const [members, setMembers] = useState<ChittiMember[]>([]);
  const [schedule, setSchedule] = useState<ChittiPeriodSchedule[]>([]);
  const [payouts, setPayouts] = useState<ChittiPayout[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [activation, setActivation] = useState<ActivationStatus | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
    blockers?: { code: string; message: string }[];
  } | null>(null);
  const [selectedMember, setSelectedMember] = useState<
    (ChittiMember & { agreement?: Agreement | null }) | null
  >(null);

  const [showAddMember, setShowAddMember] = useState(false);
  const [showAgreement, setShowAgreement] = useState<Agreement | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [c, s, m, a] = await Promise.all([
        chittiApi.getChitti(chittiId),
        chittiApi.getSummary(chittiId),
        chittiApi.listMembers(chittiId),
        chittiApi.getActivation(chittiId),
      ]);
      setChitti(c);
      setSummary(s);
      setMembers(m);
      setActivation(a);
    } catch (e) {
      console.error(e);
      setFeedback({ type: "error", message: getApiErrorMessage(e, "Could not load this Chitti.") });
    } finally { setLoading(false); }
  }, [chittiId]);

  useEffect(() => { loadData(); }, [loadData]);

  const loadMembers = async () => {
    try { setMembers(await chittiApi.listMembers(chittiId)); }
    catch (e) { console.error(e); }
  };

  const loadTab = async (tab: Tab) => {
    setActiveTab(tab);
    setSelectedMember(null);
    if (tab === "members") await loadMembers();
    if (tab === "schedule" && schedule.length === 0) {
      try { setSchedule(await chittiApi.getSchedule(chittiId)); } catch (e) { console.error(e); }
    }
    if (tab === "payouts" && payouts.length === 0) {
      try { setPayouts(await chittiApi.listPayouts(chittiId)); } catch (e) { console.error(e); }
    }
  };

  const handleStatusChange = async (action: "start" | "pause" | "resume" | "complete" | "cancel") => {
    if (actionLoading) return; // guard against double submission
    if (!confirm(`Are you sure you want to ${action} this chitti?`)) return;
    setActionLoading(action);
    setFeedback(null);
    try {
      await chittiApi.changeStatus(chittiId, action);
      // Re-read everything from the backend so the badge, counts and financials
      // show the persisted state rather than a locally guessed one.
      await loadData();
      setFeedback({
        type: "success",
        message:
          action === "start" ? "Chitti started successfully."
          : action === "pause" ? "Chitti paused."
          : action === "resume" ? "Chitti resumed."
          : action === "complete" ? "Chitti completed."
          : "Chitti cancelled.",
      });
    } catch (e: unknown) {
      const details = getApiErrorDetails<ActivationStatus>(e);
      if (details?.blockers) setActivation(details);
      setFeedback({
        type: "error",
        message: getApiErrorMessage(e, `Could not ${action} this Chitti.`),
        blockers: details?.blockers,
      });
    } finally {
      setActionLoading(null);
    }
  };

  const handleStart = async () => {
    // Explain the exact blocked prerequisites instead of sending a request
    // that is guaranteed to fail.
    if (activation && !activation.can_activate) {
      setFeedback({
        type: "error",
        message: "This Chitti cannot be started yet.",
        blockers: activation.blockers,
      });
      return;
    }
    await handleStatusChange("start");
  };

  const handleViewMember = async (member: ChittiMember) => {
    try {
      const detail = await chittiApi.getMemberDetail(chittiId, member.id);
      setSelectedMember(detail as ChittiMember & { agreement: Agreement | null });
    } catch { setSelectedMember(member); }
  };

  const handleGenerateAgreement = async (memberId: string) => {
    try {
      await chittiApi.generateAgreement(chittiId, memberId);
      const detail = await chittiApi.getMemberDetail(chittiId, memberId);
      setSelectedMember(detail as ChittiMember & { agreement: Agreement | null });
    } catch (e) { console.error(e); }
  };

  const handlePrintAgreement = async (memberId: string) => {
    try { await chittiApi.printAgreement(chittiId, memberId); } catch (e) { console.error(e); }
  };

  const handleConfirmAgreement = async (memberId: string) => {
    if (!confirm("Have you completed the physical agreement/signature?")) return;
    try {
      await chittiApi.confirmAgreement(chittiId, memberId);
      const detail = await chittiApi.getMemberDetail(chittiId, memberId);
      setSelectedMember(detail as ChittiMember & { agreement: Agreement | null });
      await loadMembers();
      setShowAgreement(null);
    } catch (e) { console.error(e); }
  };

  const handleCancelMember = async (memberId: string) => {
    const reason = prompt("Reason for cancellation (optional):");
    if (reason === null) return;
    try {
      await chittiApi.cancelMember(chittiId, memberId, reason);
      await loadMembers();
      setSelectedMember(null);
    } catch (e) { console.error(e); }
  };

  if (loading) return <DashboardLayout><div className="p-8"><PageSkeleton /></div></DashboardLayout>;
  if (!chitti || !summary) return <DashboardLayout><div className="card text-center py-12 text-surface-500">Chitti not found</div></DashboardLayout>;

  const snapshot = chitti.plan_snapshot as Record<string, unknown> | null;
  const contribRules = snapshot?.contribution_rules as Record<string, unknown> | undefined;
  const payoutRules = snapshot?.payout_rules as Record<string, unknown> | undefined;
  const progressPct = summary.total_periods > 0 ? Math.round((summary.current_period / summary.total_periods) * 100) : 0;
  const canAddMembers = chitti.status === "DRAFT" || chitti.status === "UPCOMING";
  // Enrolled members, not ACTIVE-only: pending-agreement members already hold
  // a seat and must be counted the same way the Members tab counts them.
  const memberCapacity = summary.member_capacity ?? summary.member_count;
  const currentMemberCount = summary.enrolled_members ?? members.length;
  const enrolledCustomerIds = new Set(members.map((m) => m.customer_id));

  return (
    <DashboardLayout>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <Link href="/chitti" className="rounded-lg p-2 text-surface-400 hover:bg-surface-100 hover:text-surface-600 transition-colors">
                <ArrowLeft size={18} />
              </Link>
              <div>
                <h1 className="text-2xl font-bold text-surface-900 tracking-tight">{chitti.name}</h1>
                <div className="flex items-center gap-2 mt-1">
                  <span className={cn("badge", getStatusColor(chitti.status))}>{displayStateLabel(activation?.display_state ?? chitti.status)}</span>
                  <span className="text-sm text-surface-500">{chitti.chitti_code} • {String(snapshot?.frequency ?? "MONTHLY")}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            {canAddMembers && (
              <button onClick={() => setShowAddMember(true)} className="btn-primary">
                <Plus size={16} /> Add Member
              </button>
            )}
            {chitti.status === "DRAFT" && (
              <button
                onClick={handleStart}
                disabled={actionLoading !== null}
                title={activation && !activation.can_activate ? activation.blockers.map((b) => b.message).join(" ") : undefined}
                className="btn-primary disabled:opacity-60"
              >
                <Play size={16} /> {actionLoading === "start" ? "Starting..." : "Start"}
              </button>
            )}
            {chitti.status === "RUNNING" && (
              <>
                <button onClick={() => handleStatusChange("pause")} disabled={actionLoading !== null} className="btn-secondary disabled:opacity-60"><Pause size={16} /> {actionLoading === "pause" ? "Pausing..." : "Pause"}</button>
                <button onClick={() => handleStatusChange("complete")} disabled={actionLoading !== null} className="btn-secondary disabled:opacity-60"><CheckCircle2 size={16} /> {actionLoading === "complete" ? "Completing..." : "Complete"}</button>
              </>
            )}
            {chitti.status === "PAUSED" && <button onClick={() => handleStatusChange("resume")} disabled={actionLoading !== null} className="btn-primary disabled:opacity-60"><Play size={16} /> Resume</button>}
            {(chitti.status === "DRAFT" || chitti.status === "RUNNING") && (
              <button onClick={() => handleStatusChange("cancel")} disabled={actionLoading !== null} className="btn-danger disabled:opacity-60"><XCircle size={16} /> Cancel</button>
            )}
          </div>
        </div>

        {feedback && (
          <div
            role="status"
            className={cn(
              "rounded-xl border p-4 text-sm",
              feedback.type === "error"
                ? "border-danger-100 bg-danger-50 text-danger-700"
                : "border-success-100 bg-success-50 text-success-700"
            )}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-semibold">{feedback.message}</p>
                {feedback.blockers && feedback.blockers.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {feedback.blockers.map((b) => (
                      <li key={b.code}>{b.message}</li>
                    ))}
                  </ul>
                )}
              </div>
              <button onClick={() => setFeedback(null)} className="text-xs font-medium underline">
                Dismiss
              </button>
            </div>
          </div>
        )}

        {activation && (chitti.status === "DRAFT" || chitti.status === "UPCOMING") && (
          <div className="card space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-surface-900">Activation readiness</h3>
                <p className="text-sm text-surface-500">
                  {activation.enrolled_members} of {activation.member_capacity} seats filled •{" "}
                  {activation.active_members} active • {activation.pending_agreements} pending agreement(s)
                </p>
              </div>
              <span className={cn("badge", activation.can_activate ? "badge-success" : "badge-warning")}>
                {activation.can_activate ? "Ready to start" : "Activation blocked"}
              </span>
            </div>
            {activation.blockers.length > 0 && (
              <div className="rounded-xl bg-warning-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-warning-700">
                  Must be resolved before starting
                </p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-warning-700">
                  {activation.blockers.map((b) => (
                    <li key={b.code}>{b.message}</li>
                  ))}
                </ul>
              </div>
            )}
            {activation.warnings.length > 0 && (
              <div className="rounded-xl bg-surface-50 p-3">
                <ul className="list-disc space-y-1 pl-5 text-sm text-surface-600">
                  {activation.warnings.map((w) => (
                    <li key={w.code}>{w.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Progress */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-surface-700">Period {summary.current_period} of {summary.total_periods}</span>
            <span className="text-sm font-semibold text-brand-600">{progressPct}%</span>
          </div>
          <ProgressBar value={progressPct} size="lg" color="brand" />
        </div>

        {/* Financial Summary */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[
            { label: "Total Value", value: formatCurrency(summary.total_value), icon: <IndianRupee size={18} />, color: "bg-brand-50 text-brand-600" },
            { label: "Collected", value: formatCurrency(summary.actual_collection), icon: <TrendingUp size={18} />, color: "bg-success-50 text-success-600" },
            { label: "Pending", value: formatCurrency(summary.pending_collection), icon: <TrendingDown size={18} />, color: "bg-warning-50 text-warning-600" },
            { label: "Members", value: `${currentMemberCount} / ${memberCapacity}`, icon: <Users size={18} />, color: "bg-purple-50 text-purple-600" },
          ].map((stat) => (
            <div key={stat.label} className="card flex items-center gap-4">
              <div className={cn("rounded-xl p-3", stat.color)}>{stat.icon}</div>
              <div>
                <p className="text-xs font-medium text-surface-500 uppercase">{stat.label}</p>
                <p className="text-xl font-bold text-surface-900 tabular-nums">{stat.value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Quick Info */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <div className="card text-sm">
            <div className="flex items-center gap-2 text-surface-500 mb-1"><Calendar size={14} /> Duration</div>
            <p className="font-medium text-surface-900">{formatDate(chitti.start_date)} → {formatDate(chitti.end_date)}</p>
          </div>
          <div className="card text-sm">
            <div className="flex items-center gap-2 text-surface-500 mb-1"><FileText size={14} /> Contribution</div>
            <p className="font-medium text-surface-900">
              {String(contribRules?.type || "FIXED")}
              {contribRules?.installment_amount ? ` — ${formatCurrency(Number(contribRules.installment_amount))}` : ""}
              {contribRules?.pre_lift_amount ? ` — ${formatCurrency(Number(contribRules.pre_lift_amount))} / ${formatCurrency(Number(contribRules.post_lift_amount))}` : ""}
            </p>
          </div>
          <div className="card text-sm">
            <div className="flex items-center gap-2 text-surface-500 mb-1"><TrendingUp size={14} /> Payout</div>
            <p className="font-medium text-surface-900">
              {String(payoutRules?.type || "SCHEDULED")}
              {payoutRules?.commission_percentage ? ` — ${payoutRules.commission_percentage}% commission` : ""}
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs">
          {(["overview", "members", "schedule", "payouts"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => loadTab(tab)}
              className={cn("tab", activeTab === tab && "tab-active")}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
              {tab === "members" ? ` (${currentMemberCount})` : ""}
            </button>
          ))}
        </div>

        {/* ============ OVERVIEW TAB ============ */}
        {activeTab === "overview" && (
          <div className="card">
            <h3 className="text-sm font-semibold text-surface-900 mb-4">Next Due</h3>
            {summary.next_due_date ? (
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-warning-50 p-3 text-warning-600"><Calendar size={20} /></div>
                <div>
                  <p className="text-lg font-bold text-surface-900">{formatDate(summary.next_due_date)}</p>
                  <p className="text-sm text-surface-500">{formatCurrency(summary.pending_collection)} pending</p>
                </div>
              </div>
            ) : <p className="text-surface-500">No upcoming dues</p>}
            {chitti.notes && <div className="mt-4 pt-4 border-t border-surface-100"><p className="text-sm text-surface-600">{chitti.notes}</p></div>}
          </div>
        )}

        {/* ============ MEMBERS TAB ============ */}
        {activeTab === "members" && (
          <div className="space-y-4">
            {selectedMember ? (
              <div className="card animate-fade-in">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-4">
                    <Avatar name={selectedMember.customer_name || ""} size="lg" />
                    <div>
                      <h3 className="text-lg font-semibold text-surface-900">{selectedMember.customer_name || selectedMember.customer_code}</h3>
                      <p className="text-sm text-surface-500">Member #{selectedMember.member_number} • {selectedMember.mobile_number || "—"}</p>
                    </div>
                  </div>
                  <button onClick={() => setSelectedMember(null)} className="btn-ghost text-sm"><ArrowLeft size={16} /> Back</button>
                </div>

                <div className="flex items-center gap-3 mb-6">
                  <span className={cn("badge", getStatusColor(selectedMember.status))}>{selectedMember.status.replace(/_/g, " ")}</span>
                  {canAddMembers && selectedMember.status === "PENDING_AGREEMENT" && (
                    <button onClick={() => handleGenerateAgreement(selectedMember.id)} className="btn-primary btn-sm"><FileText size={14} /> Generate Agreement</button>
                  )}
                  {canAddMembers && ["PENDING_AGREEMENT", "AGREEMENT_GENERATED", "AGREEMENT_PRINTED"].includes(selectedMember.status) && (
                    <button onClick={() => handleCancelMember(selectedMember.id)} className="btn-danger btn-sm">Cancel</button>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="rounded-xl bg-success-50 p-4"><p className="text-xs text-success-600 font-medium">Paid</p><p className="text-2xl font-bold text-success-700">{formatCurrency(selectedMember.total_paid || 0)}</p></div>
                  <div className="rounded-xl bg-warning-50 p-4"><p className="text-xs text-warning-600 font-medium">Outstanding</p><p className="text-2xl font-bold text-warning-700">{formatCurrency(selectedMember.outstanding || 0)}</p></div>
                  <div className="rounded-xl bg-brand-50 p-4"><p className="text-xs text-brand-600 font-medium">Expected</p><p className="text-2xl font-bold text-brand-700">{formatCurrency(selectedMember.total_expected || 0)}</p></div>
                  <div className="rounded-xl bg-surface-50 p-4"><p className="text-xs text-surface-500 font-medium">Lifted</p><p className="text-2xl font-bold text-surface-700">{selectedMember.lifted ? "Yes" : "No"}</p></div>
                </div>

                {/* Agreement Section */}
                {"agreement" in selectedMember && selectedMember.agreement && (
                  <div className="border-t border-surface-100 pt-6">
                    <h4 className="font-semibold text-surface-900 mb-3">Agreement</h4>
                    <div className="rounded-xl bg-surface-50 p-4">
                      <div className="grid grid-cols-2 gap-3 text-sm mb-4">
                        <div><p className="text-surface-500">Number</p><p className="font-medium">{selectedMember.agreement.agreement_number}</p></div>
                        <div><p className="text-surface-500">Status</p><span className={cn("badge", getStatusColor(selectedMember.agreement.agreement_status))}>{selectedMember.agreement.agreement_status}</span></div>
                        <div><p className="text-surface-500">Generated</p><p className="font-medium">{selectedMember.agreement.generated_at ? formatDate(selectedMember.agreement.generated_at) : "—"}</p></div>
                        <div><p className="text-surface-500">Printed</p><p className="font-medium">{selectedMember.agreement.printed_at ? formatDate(selectedMember.agreement.printed_at) : "—"} {selectedMember.agreement.print_count > 0 ? `(${selectedMember.agreement.print_count}×)` : ""}</p></div>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => setShowAgreement(selectedMember.agreement ?? null)} className="btn-secondary btn-sm"><FileText size={14} /> View</button>
                        {(selectedMember.agreement.agreement_status === "GENERATED" || selectedMember.agreement.agreement_status === "PRINTED") && (
                          <button onClick={() => handlePrintAgreement(selectedMember.id)} className="btn-primary btn-sm"><Printer size={14} /> Print</button>
                        )}
                        {selectedMember.agreement.agreement_status === "PRINTED" && (
                          <button onClick={() => handleConfirmAgreement(selectedMember.id)} className="inline-flex items-center gap-1.5 rounded-lg bg-success-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-success-700 transition-colors">
                            <CheckCircle2 size={14} /> Confirm
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {"agreement" in selectedMember && !selectedMember.agreement && canAddMembers && (
                  <div className="border-t border-surface-100 pt-6 text-center">
                    <button onClick={() => handleGenerateAgreement(selectedMember.id)} className="btn-primary"><FileText size={16} /> Generate Agreement</button>
                  </div>
                )}
              </div>
            ) : (
              <div className="card">
                {canAddMembers && (
                  <div className="flex items-center justify-between mb-6">
                    <p className="text-sm text-surface-500">Members: <span className="font-semibold text-surface-900">{currentMemberCount} / {memberCapacity}</span> • <span className="text-surface-400">{Math.max(memberCapacity - currentMemberCount, 0)} slot(s) available</span></p>
                    <button onClick={() => setShowAddMember(true)} className="btn-primary btn-sm" disabled={currentMemberCount >= memberCapacity}><Plus size={14} /> Add Member</button>
                  </div>
                )}

                {members.length === 0 ? (
                  <EmptyState icon="👥" title="No members yet" description="Add members when the chitti is in DRAFT status." action={canAddMembers ? <button onClick={() => setShowAddMember(true)} className="btn-primary"><Plus size={16} /> Add First Member</button> : undefined} />
                ) : (
                  <div className="space-y-3">
                    {members.map((m) => (
                      <div key={m.id} className="flex items-center gap-4 p-4 rounded-xl border border-surface-100 hover:border-surface-200 hover:shadow-sm transition-all cursor-pointer group" onClick={() => handleViewMember(m)}>
                        <Avatar name={m.customer_name || ""} size="md" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-surface-900 group-hover:text-brand-700 transition-colors">{m.customer_name || m.customer_code}</p>
                          <p className="text-xs text-surface-500">#{m.member_number} • {m.mobile_number || "—"}</p>
                        </div>
                        <div className="text-right hidden sm:block">
                          <p className="text-sm font-medium text-success-600">{formatCurrency(m.total_paid)}</p>
                          <p className="text-xs text-surface-500">of {formatCurrency(m.total_expected)}</p>
                        </div>
                        <span className={cn("badge", getStatusColor(m.status))}>{m.status.replace(/_/g, " ")}</span>
                        <ChevronRight size={16} className="text-surface-300 group-hover:text-brand-500 transition-colors" />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ============ SCHEDULE TAB ============ */}
        {activeTab === "schedule" && (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Period</th><th>Due Date</th><th>Expected</th><th>Collected</th><th>Pending</th><th>Payout</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {schedule.map((s) => (
                  <tr key={s.id} className={s.period_number === summary.current_period ? "bg-brand-50/50" : ""}>
                    <td className="font-medium">{s.period_number}{s.period_number === summary.current_period && <span className="ml-1 text-xs text-brand-600">current</span>}</td>
                    <td>{formatDate(s.due_date)}</td>
                    <td>{formatCurrency(s.expected_collection)}</td>
                    <td className="text-success-600 font-medium">{formatCurrency(s.actual_collection)}</td>
                    <td className="text-warning-600">{formatCurrency(s.pending_collection)}</td>
                    <td className="text-brand-600">{formatCurrency(s.actual_payout)}</td>
                    <td><span className={cn("badge", getStatusColor(s.status))}>{s.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ============ PAYOUTS TAB ============ */}
        {activeTab === "payouts" && (
          <div className="card">
            {payouts.length === 0 ? (
              <EmptyState icon="💰" title="No payouts recorded" description="Payouts are recorded as the chitti progresses." />
            ) : (
              <div className="table-container">
                <table className="table">
                  <thead><tr><th>Period</th><th>Customer</th><th>Gross</th><th>Discount</th><th>Fees</th><th>Net</th><th>Status</th></tr></thead>
                  <tbody>
                    {payouts.map((p) => (
                      <tr key={p.id}>
                        <td>{p.period_number}</td>
                        <td><div className="flex items-center gap-2"><Avatar name={p.customer_name || ""} size="sm" /><span className="font-medium">{p.customer_name || "—"}</span></div></td>
                        <td>{formatCurrency(p.gross_payout)}</td>
                        <td className="text-danger-600">{formatCurrency(p.discount_amount)}</td>
                        <td>{formatCurrency(p.fee_amount)}</td>
                        <td className="font-semibold text-success-600">{formatCurrency(p.net_payout)}</td>
                        <td><span className={cn("badge", getStatusColor(p.status))}>{p.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modals */}
      {showAddMember && <AddMemberModal chittiId={chittiId} currentCount={currentMemberCount} maxCount={memberCapacity} enrolledCustomerIds={enrolledCustomerIds} onClose={() => setShowAddMember(false)} onAdded={async () => { setShowAddMember(false); await loadData(); setFeedback({ type: "success", message: "Member enrolled successfully." }); }} />}
      {showAgreement && selectedMember && <AgreementPreviewModal agreement={showAgreement} chittiName={chitti.name} memberName={selectedMember.customer_name || ""} onClose={() => setShowAgreement(null)} onPrint={() => handlePrintAgreement(selectedMember.id)} onConfirm={() => handleConfirmAgreement(selectedMember.id)} />}
    </DashboardLayout>
  );
}
