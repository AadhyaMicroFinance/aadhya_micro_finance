import apiClient from "./api-client";
import type { ApiResponse } from "@/types";

// ==========================================
// Chitti Types
// ==========================================

export interface ChittiPlan {
  id: string;
  plan_code: string;
  name: string;
  description: string | null;
  chitti_type: string;
  total_value: number;
  currency: string;
  member_count: number;
  frequency: string;
  duration: number;
  contribution_rules: Record<string, unknown>;
  payout_rules: Record<string, unknown>;
  fee_rules: Record<string, unknown> | null;
  penalty_rules: Record<string, unknown> | null;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChittiInstance {
  id: string;
  chitti_code: string;
  plan_id: string;
  plan_name: string | null;
  name: string;
  branch: string | null;
  start_date: string;
  end_date: string;
  /** Plan capacity (kept for backwards compatibility). */
  member_count: number;
  member_capacity?: number;
  /** Members actually enrolled, matching the dashboard and Members tab. */
  enrolled_members?: number | null;
  total_value: number;
  current_period: number;
  status: string;
  notes: string | null;
  plan_snapshot: Record<string, unknown> | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChittiDashboardItem {
  id: string;
  chitti_code: string;
  name: string;
  plan_name: string | null;
  status: string;
  /** Enrolled members (any agreement state except cancelled/rejected). */
  member_count: number;
  enrolled_members?: number;
  active_members?: number;
  member_capacity?: number;
  display_state?: string;
  total_value: number;
  expected_collection: number;
  actual_collection: number;
  pending_collection: number;
  financials_source?: "contributions" | "schedule" | "not_generated";
  current_period: number;
  total_periods: number;
  next_due_date: string | null;
  start_date: string;
  end_date: string;
}

export interface ActivationBlocker {
  code: string;
  message: string;
}

export interface ActivationStatus {
  chitti_id: string;
  status: string;
  display_state: string;
  can_activate: boolean;
  blockers: ActivationBlocker[];
  warnings: ActivationBlocker[];
  enrolled_members: number;
  active_members: number;
  pending_agreements: number;
  member_capacity: number;
  available_slots: number;
  schedule_periods: number;
}

export interface MemberAgreementSummary {
  agreement_number: string;
  agreement_status: string;
  generated_at: string | null;
  printed_at: string | null;
  confirmed_at: string | null;
}

export interface ChittiMember {
  id: string;
  chitti_id: string;
  customer_id: string;
  customer_name: string | null;
  customer_code: string | null;
  mobile_number: string | null;
  member_number: number;
  payout_order: number | null;
  status: string;
  joined_at: string;
  total_expected: number;
  total_paid: number;
  outstanding: number;
  lifted?: boolean;
  lifted_at?: string | null;
  lift_period?: number | null;
  /** Net amount already received by the member, from the payout records. */
  lifted_amount?: number;
  /** Agreement state, from the same agreement record the detail view reads. */
  agreement?: MemberAgreementSummary | null;
}

export interface ChittiPeriodSchedule {
  id: string;
  chitti_id: string;
  period_number: number;
  due_date: string;
  expected_collection: number;
  actual_collection: number;
  pending_collection: number;
  expected_payout: number;
  actual_payout: number;
  status: string;
}

export interface ChittiPayout {
  id: string;
  chitti_id: string;
  member_id: string;
  customer_name: string | null;
  period_number: number;
  gross_payout: number;
  discount_amount: number;
  fee_amount: number;
  net_payout: number;
  payout_method: string | null;
  paid_at: string | null;
  status: string;
}

export interface ChittiSummary {
  chitti_id: string;
  chitti_name: string;
  status: string;
  display_state?: string;
  /** Plan capacity (kept for backwards compatibility). */
  member_count: number;
  member_capacity?: number;
  /** Members actually enrolled, matching the Members tab. */
  enrolled_members?: number;
  active_members: number;
  financials_source?: "contributions" | "schedule" | "not_generated";
  activation?: ActivationStatus;
  current_period: number;
  total_periods: number;
  total_value: number;
  expected_collection: number;
  actual_collection: number;
  pending_collection: number;
  total_payouts: number;
  outstanding: number;
  next_due_date: string | null;
  next_payout_date: string | null;
}

export interface ChittiPreview {
  periods: {
    period_number: number;
    due_date: string;
    expected_collection: number;
    expected_payout: number;
    status: string;
  }[];
  total_expected_collection: number;
  total_expected_payout: number;
  per_member_installment_schedule: {
    period: number;
    due_date: string | null;
    amount: number;
  }[];
  plan_name: string;
  chitti_type: string;
  frequency: string;
  duration: number;
  member_count: number;
  total_value: number;
}

export interface ChittiMemberPayment {
  id: string;
  amount: number;
  payment_date: string | null;
  payment_method: string | null;
  reference_number: string | null;
  notes: string | null;
}

export interface ChittiContribution {
  id: string;
  member_id: string;
  customer_name: string | null;
  period_number: number;
  due_date?: string | null;
  expected_amount: number;
  paid_amount: number;
  remaining_amount: number;
  status: string;
  payments?: ChittiMemberPayment[];
}

export interface Agreement {
  id: string;
  agreement_number: string;
  chitti_id: string;
  chitti_member_id: string;
  customer_id: string;
  agreement_date: string;
  agreement_status: string;
  agreement_snapshot: Record<string, unknown>;
  generated_at: string | null;
  printed_at: string | null;
  print_count: number;
  confirmed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
  updated_at: string;
}

// ==========================================
// API Functions
// ==========================================

export const chittiApi = {
  // ---- Plans ----
  listPlans: async (params: {
    page?: number;
    per_page?: number;
    active_only?: boolean;
  }) => {
    const res = await apiClient.get<ApiResponse<ChittiPlan[]>>("/chitti/plans", {
      params,
    });
    return res.data;
  },

  getPlan: async (id: string): Promise<ChittiPlan> => {
    const res = await apiClient.get<ApiResponse<ChittiPlan>>(
      `/chitti/plans/${id}`
    );
    return res.data.data;
  },

  createPlan: async (data: Record<string, unknown>) => {
    const res = await apiClient.post<ApiResponse<ChittiPlan>>(
      "/chitti/plans",
      data
    );
    return res.data.data;
  },

  updatePlan: async (id: string, data: Record<string, unknown>) => {
    const res = await apiClient.put<ApiResponse<ChittiPlan>>(
      `/chitti/plans/${id}`,
      data
    );
    return res.data.data;
  },

  duplicatePlan: async (id: string) => {
    const res = await apiClient.post<ApiResponse<ChittiPlan>>(
      `/chitti/plans/${id}/duplicate`
    );
    return res.data.data;
  },

  deactivatePlan: async (id: string) => {
    const res = await apiClient.post<ApiResponse<ChittiPlan>>(
      `/chitti/plans/${id}/deactivate`
    );
    return res.data.data;
  },

  activatePlan: async (id: string) => {
    const res = await apiClient.post<ApiResponse<ChittiPlan>>(
      `/chitti/plans/${id}/activate`
    );
    return res.data.data;
  },

  previewPlan: async (
    planId: string,
    data: { start_date: string; member_count?: number }
  ): Promise<ChittiPreview> => {
    const res = await apiClient.post<ApiResponse<ChittiPreview>>(
      `/chitti/plans/${planId}/preview`,
      { plan_id: planId, ...data }
    );
    return res.data.data;
  },

  // ---- Chittis ----
  listChittis: async (params: {
    page?: number;
    per_page?: number;
    status?: string;
  }) => {
    const res = await apiClient.get<ApiResponse<ChittiInstance[]>>(
      "/chitti",
      { params }
    );
    return res.data;
  },

  getChitti: async (id: string): Promise<ChittiInstance> => {
    const res = await apiClient.get<ApiResponse<ChittiInstance>>(
      `/chitti/${id}`
    );
    return res.data.data;
  },

  createChitti: async (data: {
    plan_id: string;
    name: string;
    branch?: string;
    start_date: string;
    member_count?: number;
    notes?: string;
  }) => {
    const res = await apiClient.post<ApiResponse<ChittiInstance>>(
      "/chitti",
      data
    );
    return res.data.data;
  },

  getDashboard: async (): Promise<ChittiDashboardItem[]> => {
    const res = await apiClient.get<ApiResponse<ChittiDashboardItem[]>>(
      "/chitti/dashboard"
    );
    return res.data.data;
  },

  getSummary: async (id: string): Promise<ChittiSummary> => {
    const res = await apiClient.get<ApiResponse<ChittiSummary>>(
      `/chitti/${id}/summary`
    );
    return res.data.data;
  },

  getActivation: async (id: string): Promise<ActivationStatus> => {
    const res = await apiClient.get<ApiResponse<ActivationStatus>>(
      `/chitti/${id}/activation`
    );
    return res.data.data;
  },

  changeStatus: async (
    id: string,
    action: "start" | "pause" | "resume" | "complete" | "cancel"
  ) => {
    const res = await apiClient.post<ApiResponse<ChittiInstance>>(
      `/chitti/${id}/${action}`
    );
    return res.data.data;
  },

  // ---- Members ----
  listMembers: async (chittiId: string): Promise<ChittiMember[]> => {
    const res = await apiClient.get<ApiResponse<ChittiMember[]>>(
      `/chitti/${chittiId}/members`
    );
    return res.data.data;
  },

  addMember: async (
    chittiId: string,
    data: {
      customer_id: string;
      payout_order?: number;
    }
  ) => {
    const res = await apiClient.post<ApiResponse<ChittiMember>>(
      `/chitti/${chittiId}/members`,
      data
    );
    return res.data.data;
  },

  removeMember: async (chittiId: string, memberId: string) => {
    await apiClient.delete(`/chitti/${chittiId}/members/${memberId}`);
  },

  getMemberDetail: async (
    chittiId: string,
    memberId: string
  ): Promise<ChittiMember & { agreement: Agreement | null }> => {
    const res = await apiClient.get(
      `/chitti/${chittiId}/members/${memberId}`
    );
    return res.data.data;
  },

  // ---- Agreements ----
  generateAgreement: async (
    chittiId: string,
    memberId: string
  ): Promise<Agreement> => {
    const res = await apiClient.post(
      `/chitti/${chittiId}/members/${memberId}/agreement/generate`
    );
    return res.data.data;
  },

  getAgreement: async (
    chittiId: string,
    memberId: string
  ): Promise<Agreement> => {
    const res = await apiClient.get(
      `/chitti/${chittiId}/members/${memberId}/agreement`
    );
    return res.data.data;
  },

  printAgreement: async (
    chittiId: string,
    memberId: string
  ): Promise<Agreement> => {
    const res = await apiClient.post(
      `/chitti/${chittiId}/members/${memberId}/agreement/print`
    );
    return res.data.data;
  },

  confirmAgreement: async (
    chittiId: string,
    memberId: string
  ): Promise<Agreement> => {
    const res = await apiClient.post(
      `/chitti/${chittiId}/members/${memberId}/agreement/confirm`
    );
    return res.data.data;
  },

  cancelMember: async (
    chittiId: string,
    memberId: string,
    reason?: string
  ) => {
    const res = await apiClient.post(
      `/chitti/${chittiId}/members/${memberId}/cancel`,
      { reason: reason || "" }
    );
    return res.data.data;
  },

  // ---- Schedule ----
  getSchedule: async (chittiId: string): Promise<ChittiPeriodSchedule[]> => {
    const res = await apiClient.get<ApiResponse<ChittiPeriodSchedule[]>>(
      `/chitti/${chittiId}/schedule`
    );
    return res.data.data;
  },

  getMemberContributions: async (
    chittiId: string,
    memberId: string
  ): Promise<ChittiContribution[]> => {
    const res = await apiClient.get<ApiResponse<ChittiContribution[]>>(
      `/chitti/${chittiId}/members/${memberId}/contributions`
    );
    return res.data.data;
  },

  recordContribution: async (
    chittiId: string,
    data: {
      member_id: string;
      period_number: number;
      amount: number;
      payment_method: string;
      payment_date: string;
      reference_number?: string;
      notes?: string;
      idempotency_key: string;
    }
  ) => {
    const res = await apiClient.post<ApiResponse<Record<string, unknown>>>(
      `/chitti/${chittiId}/contributions`,
      data
    );
    return res.data.data;
  },

  // ---- Payouts ----
  listPayouts: async (chittiId: string): Promise<ChittiPayout[]> => {
    const res = await apiClient.get<ApiResponse<ChittiPayout[]>>(
      `/chitti/${chittiId}/payouts`
    );
    return res.data.data;
  },

  recordPayout: async (
    chittiId: string,
    data: {
      member_id: string;
      period_number: number;
      gross_payout: number;
      discount_amount?: number;
      fee_amount?: number;
      net_payout: number;
      payout_method: string;
    }
  ) => {
    const res = await apiClient.post<ApiResponse<Record<string, unknown>>>(
      `/chitti/${chittiId}/payouts`,
      data
    );
    return res.data.data;
  },
};
