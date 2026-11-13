import apiClient from "./api-client";
import type { ApiResponse } from "@/types";

// ==========================================
// Report Types
// ==========================================

export interface DailySummary {
  date: string;
  expected_total: number;
  expected_count: number;
  finance_expected: number;
  chitti_expected: number;
  collected_total: number;
  finance_collected: number;
  chitti_collected: number;
  reversals_total: number;
  finance_reversals: number;
  chitti_reversals: number;
  net_collections: number;
  finance_net: number;
  chitti_net: number;
  pending_total: number;
  finance_pending: number;
  chitti_pending: number;
  collection_rate: number;
}

export interface CollectionByUser {
  user_id: string | null;
  full_name: string;
  username: string;
  role: string;
  finance_collected: number;
  chitti_collected: number;
  collected_total: number;
  payment_count: number;
}

export interface CollectionByMethod {
  method: string;
  finance_total: number;
  chitti_total: number;
  total: number;
  count: number;
}

export interface PendingDetail {
  source: "FINANCE" | "CHITTI";
  reference_id: string;
  account_number: string | null;
  customer_id: string | null;
  customer_name: string | null;
  customer_code: string | null;
  mobile_number: string | null;
  period_label: string;
  chitti_name?: string | null;
  member_number?: number | null;
  expected: number;
  paid: number;
  pending: number;
  status: string;
}

export interface DayPayment {
  id: string;
  transaction_id: string;
  customer_name: string;
  customer_code: string | null;
  collector_name: string;
  amount: number;
  payment_method: string;
  status: string;
  is_reversal: boolean;
  source: "FINANCE" | "CHITTI" | "OTHER";
}

export interface DailyReport extends DailySummary {
  by_user: CollectionByUser[];
  by_method: CollectionByMethod[];
  pending_details: PendingDetail[];
  payments: DayPayment[];
}

export interface ChittiPlanMetrics {
  plan_id: string;
  total_chittis: number;
  active_chittis: number;
  completed_chittis: number;
  total_members: number;
  total_expected: number;
  total_collected: number;
  total_pending: number;
  total_payouts: number;
  collection_rate: number;
  by_status: Record<string, number>;
}

// ==========================================
// API Functions
// ==========================================

export const reportApi = {
  getDailyReport: async (date?: string): Promise<DailyReport> => {
    const res = await apiClient.get<ApiResponse<DailyReport>>("/reports/daily", {
      params: date ? { date } : {},
    });
    return res.data.data;
  },

  getDailySummary: async (date?: string): Promise<DailySummary> => {
    const res = await apiClient.get<ApiResponse<DailySummary>>(
      "/reports/daily/summary",
      { params: date ? { date } : {} }
    );
    return res.data.data;
  },

  getChittiPlanMetrics: async (planId: string): Promise<ChittiPlanMetrics> => {
    const res = await apiClient.get<ApiResponse<ChittiPlanMetrics>>(
      `/reports/chitti-plans/${planId}/metrics`
    );
    return res.data.data;
  },
};
