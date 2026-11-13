"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  CheckCircle2,
  FileText,
  IndianRupee,
  Loader2,
  Plus,
  Printer,
  Search,
} from "lucide-react";
import {
  chittiApi,
  type ChittiContribution,
  type ChittiMember,
} from "@/services/chitti";
import { formatCurrency, formatDate, cn, getStatusColor } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import EmptyState from "@/components/ui/EmptyState";
import { getApiErrorMessage } from "@/services/api-client";

const PAGE_SIZE = 10;

const MEMBER_STATUS_LABELS: Record<string, string> = {
  PENDING_AGREEMENT: "Pending agreement",
  AGREEMENT_GENERATED: "Agreement generated",
  AGREEMENT_PRINTED: "Awaiting signature",
  ACTIVE: "Active",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  REJECTED: "Rejected",
  LEFT: "Left",
  REPLACED: "Replaced",
};

const AGREEMENT_LABELS: Record<string, string> = {
  DRAFT: "Draft",
  GENERATED: "Generated",
  PRINTED: "Pending confirmation",
  CONFIRMED: "Confirmed",
  CANCELLED: "Cancelled",
};

type SortKey = "name" | "outstanding_desc" | "outstanding_asc" | "payment" | "recent";
type AgreementAction = "generate" | "print" | "confirm";

export function memberStatusLabel(status: string): string {
  return MEMBER_STATUS_LABELS[status] ?? status.replace(/_/g, " ").toLowerCase();
}

export function agreementStatusLabel(status?: string | null): string {
  if (!status) return "Not generated";
  return AGREEMENT_LABELS[status] ?? status.replace(/_/g, " ").toLowerCase();
}

function agreementTone(status?: string | null): string {
  if (!status) return "bg-surface-100 text-surface-600 ring-1 ring-surface-200";
  if (status === "CONFIRMED") return "bg-success-50 text-success-700 ring-1 ring-success-200";
  if (status === "PRINTED") return "bg-warning-50 text-warning-700 ring-1 ring-warning-200";
  if (status === "GENERATED") return "bg-brand-50 text-brand-700 ring-1 ring-brand-200";
  if (status === "CANCELLED") return "bg-danger-50 text-danger-700 ring-1 ring-danger-200";
  return "bg-surface-100 text-surface-600 ring-1 ring-surface-200";
}

function dateOrDash(value?: string | null): string {
  return value ? formatDate(value) : "—";
}

function paymentStatus(member: ChittiMember): { label: string; tone: string } {
  const outstanding = Number(member.outstanding || 0);
  const paid = Number(member.total_paid || 0);
  if (outstanding <= 0 && Number(member.total_expected || 0) > 0) {
    return { label: "Fully paid", tone: "text-success-600" };
  }
  if (paid > 0) return { label: "Partially paid", tone: "text-warning-600" };
  return { label: "Not paid", tone: "text-surface-500" };
}

function moneyBlock(label: string, value: string, tone: string) {
  return (
    <div key={label} className="min-w-0">
      <p className="text-[10px] font-semibold uppercase leading-tight text-surface-400">{label}</p>
      <p className={cn("truncate text-sm font-semibold tabular-nums", tone)}>{value}</p>
    </div>
  );
}

export default function ChittiMembersPanel({
  chittiId,
  chittiStatus,
  members,
  capacity,
  enrolledCount,
  canAddMembers,
  onAddMember,
  onRefresh,
  onCollect,
  onOpenAgreement,
  onNotify,
}: {
  chittiId: string;
  chittiStatus: string;
  members: ChittiMember[];
  capacity: number;
  enrolledCount: number;
  canAddMembers: boolean;
  onAddMember: () => void;
  onRefresh: () => Promise<void>;
  onCollect: (member: ChittiMember) => void;
  onOpenAgreement: (member: ChittiMember) => void | Promise<void>;
  onNotify: (type: "success" | "error", message: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [memberFilter, setMemberFilter] = useState("all");
  const [agreementFilter, setAgreementFilter] = useState("all");
  const [sort, setSort] = useState<SortKey>("name");
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [history, setHistory] = useState<Record<string, ChittiContribution[]>>({});
  const [historyLoading, setHistoryLoading] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<Record<string, string>>({});
  const [actionKey, setActionKey] = useState<string | null>(null);

  const memberStatuses = useMemo(
    () => Array.from(new Set(members.map((m) => m.status))),
    [members]
  );
  const agreementStates = useMemo(
    () =>
      Array.from(
        new Set(
          members.map((m) =>
            m.agreement?.agreement_status ? m.agreement.agreement_status : "NOT_GENERATED"
          )
        )
      ),
    [members]
  );

  // Filters, sorting and paging are view-only — every figure comes from the API.
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const filtered = members.filter((m) => {
      if (memberFilter !== "all" && m.status !== memberFilter) return false;
      if (agreementFilter !== "all") {
        const state = m.agreement?.agreement_status ?? "NOT_GENERATED";
        if (state !== agreementFilter) return false;
      }
      if (!needle) return true;
      return (
        (m.customer_name ?? "").toLowerCase().includes(needle) ||
        (m.customer_code ?? "").toLowerCase().includes(needle) ||
        String(m.member_number) === needle.replace("#", "") ||
        `#${m.member_number}` === needle ||
        (m.mobile_number ?? "").includes(needle)
      );
    });

    const rank = (m: ChittiMember) =>
      Number(m.outstanding || 0) <= 0 && Number(m.total_expected || 0) > 0
        ? 0
        : Number(m.total_paid || 0) > 0
          ? 1
          : 2;

    return [...filtered].sort((a, b) => {
      switch (sort) {
        case "outstanding_desc":
          return Number(b.outstanding || 0) - Number(a.outstanding || 0);
        case "outstanding_asc":
          return Number(a.outstanding || 0) - Number(b.outstanding || 0);
        case "payment":
          return rank(a) - rank(b) || Number(b.outstanding || 0) - Number(a.outstanding || 0);
        case "recent":
          return String(b.joined_at).localeCompare(String(a.joined_at));
        default:
          return (a.customer_name ?? "").localeCompare(b.customer_name ?? "");
      }
    });
  }, [members, search, memberFilter, agreementFilter, sort]);

  useEffect(() => {
    setPage(1);
  }, [search, memberFilter, agreementFilter, sort]);

  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageItems = visible.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const from = visible.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const to = Math.min(currentPage * PAGE_SIZE, visible.length);

  const loadHistory = useCallback(
    async (memberId: string) => {
      setHistoryLoading(memberId);
      setHistoryError((prev) => ({ ...prev, [memberId]: "" }));
      try {
        const rows = await chittiApi.getMemberContributions(chittiId, memberId);
        setHistory((prev) => ({ ...prev, [memberId]: rows }));
      } catch (e) {
        setHistoryError((prev) => ({
          ...prev,
          [memberId]: getApiErrorMessage(e, "Could not load the installment history."),
        }));
      } finally {
        setHistoryLoading(null);
      }
    },
    [chittiId]
  );

  const toggle = (member: ChittiMember) => {
    setExpandedId((current) => (current === member.id ? null : member.id));
    if (expandedId !== member.id && !history[member.id]) loadHistory(member.id);
  };

  const memberName = (member: ChittiMember) =>
    member.customer_name || member.customer_code || `Member #${member.member_number}`;

  const runAction = async (member: ChittiMember, action: AgreementAction) => {
    if (actionKey) return;
    const key = `${member.id}:${action}`;
    setActionKey(key);
    try {
      if (action === "generate") {
        await chittiApi.generateAgreement(chittiId, member.id);
        onNotify("success", `Agreement generated for ${memberName(member)}.`);
      } else if (action === "print") {
        await chittiApi.printAgreement(chittiId, member.id);
        onNotify("success", `Agreement recorded as printed for ${memberName(member)}.`);
      } else {
        if (!confirm("Have you completed the physical agreement/signature?")) return;
        await chittiApi.confirmAgreement(chittiId, member.id);
        onNotify("success", `Agreement confirmed for ${memberName(member)}.`);
      }
      await onRefresh();
    } catch (e) {
      onNotify(
        "error",
        getApiErrorMessage(e, `Could not ${action} the agreement for ${memberName(member)}.`)
      );
    } finally {
      setActionKey(null);
    }
  };

  const cancelEnrollment = async (member: ChittiMember) => {
    const reason = prompt(`Reason for cancelling ${memberName(member)}'s enrollment (optional):`);
    if (reason === null) return;
    // Cancel the membership record only; collected money and ledger rows are kept.
    const key = `${member.id}:cancel`;
    setActionKey(key);
    try {
      await chittiApi.cancelMember(chittiId, member.id, reason);
      onNotify("success", `${memberName(member)}'s enrollment was cancelled.`);
      await onRefresh();
    } catch (e) {
      onNotify("error", getApiErrorMessage(e, "Could not cancel this enrollment."));
    } finally {
      setActionKey(null);
    }
  };

  const renderActions = (member: ChittiMember, variant: "row" | "expanded") => {
    const agreement = member.agreement;
    const busy = (action: AgreementAction) => actionKey === `${member.id}:${action}`;
    const spinner = <Loader2 size={13} className="animate-spin" />;

    if (!agreement) {
      return (
        <>
          <button
            onClick={() => runAction(member, "generate")}
            disabled={!canAddMembers || actionKey !== null}
            className="btn-primary btn-sm"
            title={
              canAddMembers
                ? "Generate the agreement for this member"
                : "Agreements can be generated while the chitti is a draft"
            }
          >
            {busy("generate") ? spinner : <FileText size={13} />}
            {variant === "expanded" ? "Generate agreement" : "Generate"}
          </button>
          {variant === "expanded" && (
            <span className="text-xs text-surface-500">
              Print and confirm become available after generation.
            </span>
          )}
        </>
      );
    }

    return (
      <>
        <button onClick={() => onOpenAgreement(member)} className="btn-secondary btn-sm">
          <FileText size={13} /> View
        </button>
        <button
          onClick={() => runAction(member, "print")}
          disabled={actionKey !== null}
          className="btn-secondary btn-sm"
        >
          {busy("print") ? spinner : <Printer size={13} />} Print
        </button>
        {agreement.agreement_status === "PRINTED" && (
          <button
            onClick={() => runAction(member, "confirm")}
            disabled={actionKey !== null}
            className="btn-primary btn-sm"
          >
            {busy("confirm") ? spinner : <CheckCircle2 size={13} />} Confirm
          </button>
        )}
      </>
    );
  };

  const renderAgreementCell = (member: ChittiMember) => {
    const agreement = member.agreement;
    return (
      <div className="min-w-0">
        <span className={cn("badge text-[10px]", agreementTone(agreement?.agreement_status))}>
          {agreementStatusLabel(agreement?.agreement_status)}
        </span>
        <p className="mt-1 truncate text-[11px] text-surface-500">
          {agreement?.agreement_number ?? "No agreement yet"}
        </p>
        {agreement && (
          <p className="text-[10px] text-surface-400">
            Gen {dateOrDash(agreement.generated_at)} · Prt {dateOrDash(agreement.printed_at)}
          </p>
        )}
      </div>
    );
  };

  const renderExpanded = (member: ChittiMember) => {
    const rows = history[member.id];
    const agreement = member.agreement;
    return (
      <MemberExpanded
        member={member}
        rows={rows}
        loading={historyLoading === member.id}
        error={historyError[member.id]}
        canManageAgreement={canAddMembers}
        canCollect={chittiStatus === "RUNNING" && member.status === "ACTIVE"}
        canCancel={
          canAddMembers &&
          ["PENDING_AGREEMENT", "AGREEMENT_GENERATED", "AGREEMENT_PRINTED"].includes(member.status)
        }
        actionBusy={actionKey}
        onCollect={() => onCollect(member)}
        onCancel={() => cancelEnrollment(member)}
        agreementActions={renderActions(member, "expanded")}
        agreementNumber={agreement?.agreement_number}
        agreementLabel={agreementStatusLabel(agreement?.agreement_status)}
        agreementToneClass={agreementTone(agreement?.agreement_status)}
        generated={dateOrDash(agreement?.generated_at)}
        printed={dateOrDash(agreement?.printed_at)}
        confirmed={dateOrDash(agreement?.confirmed_at)}
      />
    );
  };

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="card space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <h3 className="text-base font-semibold text-surface-900">Members</h3>
              <span className="text-xs text-surface-500">
                {enrolledCount}/{capacity} seats
              </span>
            </div>
            <p className="text-xs text-surface-500">
              Money and agreement state for every member — expand a row for installment history.
            </p>
          </div>
          {canAddMembers && (
            <button
              onClick={onAddMember}
              disabled={enrolledCount >= capacity}
              className="btn-primary btn-sm w-full sm:w-auto"
            >
              <Plus size={14} /> Add member
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <div className="relative sm:col-span-2 xl:col-span-1">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
            />
            <input
              className="input-field py-2.5 pl-9 text-sm"
              placeholder="Search name, member ID or phone"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            className="input-field py-2.5 text-sm"
            value={memberFilter}
            onChange={(e) => setMemberFilter(e.target.value)}
            aria-label="Filter by membership status"
          >
            <option value="all">All membership statuses</option>
            {memberStatuses.map((s) => (
              <option key={s} value={s}>
                {memberStatusLabel(s)}
              </option>
            ))}
          </select>
          <select
            className="input-field py-2.5 text-sm"
            value={agreementFilter}
            onChange={(e) => setAgreementFilter(e.target.value)}
            aria-label="Filter by agreement status"
          >
            <option value="all">All agreement statuses</option>
            {agreementStates.map((s) => (
              <option key={s} value={s}>
                {s === "NOT_GENERATED" ? "Not generated" : agreementStatusLabel(s)}
              </option>
            ))}
          </select>
          <select
            className="input-field py-2.5 text-sm"
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            aria-label="Sort members"
          >
            <option value="name">Sort: Name (A–Z)</option>
            <option value="outstanding_desc">Sort: Outstanding (high → low)</option>
            <option value="outstanding_asc">Sort: Outstanding (low → high)</option>
            <option value="payment">Sort: Payment status</option>
            <option value="recent">Sort: Recently joined</option>
          </select>
        </div>
      </div>

      {members.length === 0 ? (
        <EmptyState
          icon="👥"
          title="No members yet"
          description="Add members when the chitti is in DRAFT status."
          action={
            canAddMembers ? (
              <button onClick={onAddMember} className="btn-primary">
                <Plus size={16} /> Add First Member
              </button>
            ) : undefined
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="No members match"
          description="Try another search, status filter or sort order."
        />
      ) : (
        <div className="card overflow-hidden p-0 sm:p-0">
          {/* Desktop / tablet: compact table, extra columns appear as width allows */}
          <table className="hidden w-full text-sm md:table">
            <thead className="bg-surface-50/70 text-left text-[10px] uppercase tracking-wide text-surface-500">
              <tr>
                <th className="px-3 py-2.5 font-semibold">Member</th>
                <th className="px-3 py-2.5 font-semibold">Status</th>
                <th className="px-3 py-2.5 text-right font-semibold">Paid</th>
                <th className="px-3 py-2.5 text-right font-semibold">Outstanding</th>
                <th className="hidden px-3 py-2.5 text-right font-semibold xl:table-cell">
                  Expected
                </th>
                <th className="hidden px-3 py-2.5 text-right font-semibold xl:table-cell">
                  Lifted
                </th>
                <th className="hidden px-3 py-2.5 font-semibold lg:table-cell">Agreement</th>
                <th className="px-3 py-2.5 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pageItems.map((member) => {
                const expanded = expandedId === member.id;
                const pay = paymentStatus(member);
                return (
                  <Fragment key={member.id}>
                    <tr
                      className={cn(
                        "border-t border-surface-100 align-top transition-colors",
                        expanded ? "bg-brand-50/30" : "hover:bg-surface-50/50"
                      )}
                    >
                      <td className="px-3 py-3">
                        <button
                          onClick={() => toggle(member)}
                          className="flex min-w-0 items-center gap-2.5 text-left"
                          aria-expanded={expanded}
                        >
                          <Avatar name={member.customer_name || ""} size="sm" />
                          <div className="min-w-0">
                            <p className="truncate font-semibold text-surface-900">
                              {memberName(member)}
                            </p>
                            <p className="text-[11px] text-surface-500">
                              #{member.member_number} · {member.customer_code ?? "—"}
                            </p>
                            <p className={cn("text-[11px]", pay.tone)}>
                              {member.mobile_number || "—"} · {pay.label}
                            </p>
                          </div>
                        </button>
                      </td>
                      <td className="px-3 py-3">
                        <span className={cn("badge text-[10px]", getStatusColor(member.status))}>
                          {memberStatusLabel(member.status)}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-success-600">
                        {formatCurrency(Number(member.total_paid || 0))}
                      </td>
                      <td
                        className={cn(
                          "px-3 py-3 text-right font-semibold tabular-nums",
                          Number(member.outstanding || 0) > 0
                            ? "text-warning-600"
                            : "text-success-600"
                        )}
                      >
                        {formatCurrency(Number(member.outstanding || 0))}
                      </td>
                      <td className="hidden px-3 py-3 text-right tabular-nums text-surface-600 xl:table-cell">
                        {formatCurrency(Number(member.total_expected || 0))}
                      </td>
                      <td className="hidden px-3 py-3 text-right tabular-nums text-surface-600 xl:table-cell">
                        {Number(member.lifted_amount || 0) > 0
                          ? formatCurrency(Number(member.lifted_amount || 0))
                          : "—"}
                      </td>
                      <td className="hidden px-3 py-3 lg:table-cell">
                        {renderAgreementCell(member)}
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center justify-end gap-1.5">
                          <div className="flex flex-col items-end gap-1.5 sm:flex-row sm:items-center">
                            {renderActions(member, "row")}
                          </div>
                          <button
                            onClick={() => toggle(member)}
                            className="rounded-lg p-1.5 text-surface-400 hover:bg-surface-100 hover:text-surface-600"
                            aria-label={expanded ? "Collapse member details" : "Expand member details"}
                            aria-expanded={expanded}
                          >
                            <ChevronDown
                              size={16}
                              className={cn("transition-transform", expanded && "rotate-180")}
                            />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="border-t border-surface-100 bg-surface-50/60">
                        <td colSpan={8} className="px-3 pb-4 pt-3">
                          {renderExpanded(member)}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>

          {/* Phones: compact summary cards with the same metrics and actions */}
          <div className="divide-y divide-surface-100 md:hidden">
            {pageItems.map((member) => {
              const expanded = expandedId === member.id;
              const pay = paymentStatus(member);
              return (
                <div key={member.id} className={cn("p-3", expanded && "bg-surface-50/60")}>
                  <button
                    onClick={() => toggle(member)}
                    className="flex w-full items-start justify-between gap-2 text-left"
                    aria-expanded={expanded}
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <Avatar name={member.customer_name || ""} size="sm" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-surface-900">
                          {memberName(member)}
                        </p>
                        <p className="text-[11px] text-surface-500">
                          #{member.member_number} · {member.customer_code ?? "—"} ·{" "}
                          {member.mobile_number || "—"}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <span className={cn("badge text-[10px]", getStatusColor(member.status))}>
                        {memberStatusLabel(member.status)}
                      </span>
                      <ChevronDown
                        size={16}
                        className={cn(
                          "text-surface-400 transition-transform",
                          expanded && "rotate-180"
                        )}
                      />
                    </div>
                  </button>

                  <div className="mt-2 grid grid-cols-2 gap-1.5 rounded-lg bg-surface-50 p-2">
                    {moneyBlock(
                      "Paid",
                      formatCurrency(Number(member.total_paid || 0)),
                      "text-success-600"
                    )}
                    {moneyBlock(
                      "Outstanding",
                      formatCurrency(Number(member.outstanding || 0)),
                      Number(member.outstanding || 0) > 0 ? "text-warning-600" : "text-success-600"
                    )}
                    {moneyBlock(
                      "Expected",
                      formatCurrency(Number(member.total_expected || 0)),
                      "text-surface-700"
                    )}
                    {moneyBlock(
                      "Lifted",
                      Number(member.lifted_amount || 0) > 0
                        ? formatCurrency(Number(member.lifted_amount || 0))
                        : "—",
                      "text-surface-700"
                    )}
                  </div>

                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <span
                        className={cn(
                          "badge text-[10px]",
                          agreementTone(member.agreement?.agreement_status)
                        )}
                      >
                        {agreementStatusLabel(member.agreement?.agreement_status)}
                      </span>
                      <p className="mt-1 truncate text-[10px] text-surface-500">
                        {member.agreement?.agreement_number ?? "No agreement yet"}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {renderActions(member, "row")}
                    </div>
                  </div>

                  {expanded && <div className="mt-3">{renderExpanded(member)}</div>}
                </div>
              );
            })}
          </div>

          {visible.length > PAGE_SIZE && (
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-surface-100 px-3 py-2.5 text-xs text-surface-500">
              <span>
                Showing {from}–{to} of {visible.length} members
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="btn-secondary btn-sm disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="px-1 font-medium text-surface-600">
                  {currentPage} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="btn-secondary btn-sm disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MemberExpanded({
  member,
  rows,
  loading,
  error,
  canManageAgreement,
  canCollect,
  canCancel,
  actionBusy,
  onCollect,
  onCancel,
  agreementActions,
  agreementNumber,
  agreementLabel,
  agreementToneClass,
  generated,
  printed,
  confirmed,
}: {
  member: ChittiMember;
  rows?: ChittiContribution[];
  loading: boolean;
  error?: string;
  canManageAgreement: boolean;
  canCollect: boolean;
  canCancel: boolean;
  actionBusy: string | null;
  onCollect: () => void;
  onCancel: () => void;
  agreementActions: React.ReactNode;
  agreementNumber?: string;
  agreementLabel: string;
  agreementToneClass: string;
  generated: string;
  printed: string;
  confirmed: string;
}) {
  const [onlyUnpaid, setOnlyUnpaid] = useState(false);
  const installmentRows = (rows ?? []).filter(
    (r) => !onlyUnpaid || Number(r.remaining_amount || 0) > 0
  );

  return (
    <div className="space-y-3">
      {/* Financial + agreement summary */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-surface-100 bg-white p-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-surface-400">
            Financial summary
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div>
              <p className="text-[10px] uppercase text-surface-400">Paid</p>
              <p className="text-sm font-semibold text-success-600">
                {formatCurrency(Number(member.total_paid || 0))}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-surface-400">Outstanding</p>
              <p className="text-sm font-semibold text-warning-600">
                {formatCurrency(Number(member.outstanding || 0))}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-surface-400">Expected</p>
              <p className="text-sm font-semibold text-surface-900">
                {formatCurrency(Number(member.total_expected || 0))}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase text-surface-400">Lifted</p>
              <p className="text-sm font-semibold text-surface-900">
                {Number(member.lifted_amount || 0) > 0
                  ? formatCurrency(Number(member.lifted_amount || 0))
                  : "—"}
              </p>
              {member.lifted_at && (
                <p className="text-[10px] text-surface-400">{formatDate(member.lifted_at)}</p>
              )}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {canCollect && (
              <button onClick={onCollect} className="btn-primary btn-sm">
                <IndianRupee size={13} /> Collect contribution
              </button>
            )}
            {canCancel && (
              <button
                onClick={onCancel}
                disabled={actionBusy !== null}
                className="btn-secondary btn-sm text-danger-600"
              >
                Cancel enrollment
              </button>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-surface-100 bg-white p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[10px] font-bold uppercase tracking-wider text-surface-400">
              Agreement
            </p>
            <span className={cn("badge text-[10px]", agreementToneClass)}>{agreementLabel}</span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
            <div>
              <p className="text-surface-400">Number</p>
              <p className="font-medium text-surface-900">{agreementNumber ?? "—"}</p>
            </div>
            <div>
              <p className="text-surface-400">Generated</p>
              <p className="font-medium text-surface-900">{generated}</p>
            </div>
            <div>
              <p className="text-surface-400">Printed</p>
              <p className="font-medium text-surface-900">{printed}</p>
            </div>
            <div>
              <p className="text-surface-400">Confirmed</p>
              <p className="font-medium text-surface-900">{confirmed}</p>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">{agreementActions}</div>
        </div>
      </div>

      {/* Installment history */}
      <div className="rounded-xl border border-surface-100 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-100 px-3 py-2">
          <p className="text-[10px] font-bold uppercase tracking-wider text-surface-400">
            Installment history
          </p>
          <label className="flex items-center gap-1.5 text-[11px] text-surface-600">
            <input
              type="checkbox"
              checked={onlyUnpaid}
              onChange={(e) => setOnlyUnpaid(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-surface-300"
            />
            Only unpaid
          </label>
        </div>

        {loading ? (
          <p className="flex items-center gap-2 px-3 py-4 text-xs text-surface-500">
            <Loader2 size={14} className="animate-spin" /> Loading installments…
          </p>
        ) : error ? (
          <p className="px-3 py-3 text-xs text-danger-600">{error}</p>
        ) : !rows || rows.length === 0 ? (
          <p className="px-3 py-3 text-xs text-surface-500">
            No installments yet. They are created when the chitti starts.
          </p>
        ) : installmentRows.length === 0 ? (
          <p className="px-3 py-3 text-xs text-success-600">
            Every installment is fully paid — nothing outstanding.
          </p>
        ) : (
          <div className="divide-y divide-surface-50">
            {installmentRows.map((row) => {
              const payments = row.payments ?? [];
              return (
                <div key={row.id} className="px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold text-surface-900">
                        Period {row.period_number}
                      </span>
                      <span className="text-[11px] text-surface-500">
                        Due {row.due_date ? formatDate(row.due_date) : "—"}
                      </span>
                      <span
                        className={cn(
                          "badge text-[10px]",
                          row.status === "PAID"
                            ? "badge-success"
                            : row.status === "PARTIALLY_PAID"
                              ? "badge-warning"
                              : row.status === "OVERDUE"
                                ? "badge-danger"
                                : "badge-neutral"
                        )}
                      >
                        {row.status.replace(/_/g, " ").toLowerCase()}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] tabular-nums">
                      <span className="text-surface-500">
                        Expected{" "}
                        <span className="font-medium text-surface-800">
                          {formatCurrency(Number(row.expected_amount || 0))}
                        </span>
                      </span>
                      <span className="text-surface-500">
                        Paid{" "}
                        <span className="font-medium text-success-600">
                          {formatCurrency(Number(row.paid_amount || 0))}
                        </span>
                      </span>
                      <span className="text-surface-500">
                        Remaining{" "}
                        <span className="font-medium text-warning-600">
                          {formatCurrency(Number(row.remaining_amount || 0))}
                        </span>
                      </span>
                    </div>
                  </div>

                  {payments.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {payments.map((p) => (
                        <li key={p.id} className="text-[11px] text-surface-500">
                          {p.payment_date ? formatDate(p.payment_date) : "—"} ·{" "}
                          {formatCurrency(Number(p.amount || 0))} ·{" "}
                          {(p.payment_method ?? "—").replace(/_/g, " ").toLowerCase()}
                          {p.reference_number ? ` · Ref ${p.reference_number}` : ""}
                          {p.notes ? ` · ${p.notes}` : ""}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
