import apiClient from "./api-client";
import type { ApiResponse } from "@/types";

// ==========================================
// Chitti Analytics Types
// All money values are INR numbers (display only).
// ==========================================

export interface AnalyticsFilters {
  start_date: string;
  end_date: string;
  chitti_id: string | null;
  member_id: string | null;
  payment_mode: string | null;
  status: string | null;
}

export interface TodayMetrics {
  date: string;
  expected: number;
  collected: number;
  pending: number;
  members_paid: number;
  members_due: number;
  members_unpaid: number;
  partial_count: number;
  overdue_count: number;
  payments_count: number;
  by_method: MethodTotal[];
}

export interface MethodTotal {
  mode: string;
  amount: number;
  count: number;
}

export interface AnalyticsKpis {
  total_chittis: number;
  active_chittis: number;
  completed_chittis: number;
  total_chitti_value: number;
  total_expected: number;
  total_collected: number;
  total_pending: number;
  total_overdue: number;
  total_members: number;
  collection_efficiency: number;
  range_expected: number;
  range_collected: number;
  range_pending: number;
  today_expected: number;
  today_collected: number;
  today_pending: number;
  overdue_amount: number;
  overdue_members: number;
  comparison: {
    previous_collected: number;
    change_amount: number;
    change_pct: number;
  };
}

export interface DailyPoint {
  date: string;
  expected: number;
  collected: number;
  pending: number;
}

export interface MonthlyPoint {
  month: string;
  label: string;
  expected: number;
  collected: number;
}

export interface StatusBucket {
  status: string;
  count: number;
  amount: number;
}

export interface ChittiMetric {
  id: string;
  chitti_code: string;
  name: string;
  plan_name: string | null;
  status: string;
  branch: string | null;
  start_date: string;
  end_date: string;
  total_value: number;
  member_count: number;
  active_members: number;
  expected: number;
  collected: number;
  pending: number;
  overdue: number;
  today_collection: number;
  month_collection: number;
  remaining: number;
  collection_pct: number;
  next_due_date: string | null;
  current_period: number;
  total_periods: number;
}

export type MemberPaymentStatus =
  | "PAID"
  | "PARTIALLY_PAID"
  | "PENDING"
  | "OVERDUE"
  | "ADVANCE_PAID";

export interface MemberPaymentRow {
  member_id: string;
  chitti_id: string;
  member_number: number;
  member_name: string;
  customer_code: string | null;
  mobile_number: string | null;
  chitti_name: string | null;
  expected_total: number;
  paid_total: number;
  pending_total: number;
  due_total: number;
  due_pending: number;
  advance_amount: number;
  overdue_amount: number;
  status: MemberPaymentStatus;
  payment_date: string | null;
  payment_mode: string | null;
  last_payment_amount: number;
}

export interface PendingDetail {
  member_id: string;
  member_name: string;
  mobile_number: string | null;
  chitti_id: string;
  chitti_name: string;
  period_number: number;
  due_date: string | null;
  days_overdue: number;
  amount_pending: number;
  amount_expected: number;
  amount_paid: number;
  last_payment_date: string | null;
  total_outstanding: number;
  status: string;
}

export interface LedgerRow {
  id: string;
  transaction_id: string;
  member_id: string | null;
  member_name: string;
  chitti_id: string;
  chitti_name: string;
  transaction_type: string;
  amount: number;
  payment_method: string | null;
  reference_number: string | null;
  period_number: number | null;
  received_by: string | null;
  status: string;
  remarks: string | null;
  created_at: string;
  payment_date?: string | null;
}

export interface FinancialSummary {
  total_receivable: number;
  total_received: number;
  total_outstanding: number;
  total_overdue: number;
  total_advance: number;
  total_refunds: number;
  total_adjustments: number;
  daily_collection: number;
  monthly_collection: number;
  yearly_collection: number;
}

export interface ChittiOverview {
  filters: AnalyticsFilters;
  today: TodayMetrics;
  kpis: AnalyticsKpis;
  daily: {
    series: DailyPoint[];
    expected: number;
    collected: number;
    pending: number;
    by_method: MethodTotal[];
  };
  monthly: { series: MonthlyPoint[] };
  status_distribution: StatusBucket[];
  mode_distribution: MethodTotal[];
  chitti_metrics: ChittiMetric[];
  member_rows: MemberPaymentRow[];
  pending_details: PendingDetail[];
  transactions: LedgerRow[];
  financial_summary: FinancialSummary;
}

export interface AnalyticsQuery {
  start_date?: string;
  end_date?: string;
  chitti_id?: string;
  member_id?: string;
  payment_mode?: string;
  status?: string;
}

// ==========================================
// API Functions
// ==========================================

export const analyticsApi = {
  getOverview: async (params: AnalyticsQuery = {}): Promise<ChittiOverview> => {
    const res = await apiClient.get<ApiResponse<ChittiOverview>>(
      "/analytics/chitti/overview",
      { params }
    );
    return res.data.data;
  },

  getTransactions: async (
    params: AnalyticsQuery & { page?: number; per_page?: number; search?: string }
  ): Promise<{ data: LedgerRow[]; meta: Record<string, number> }> => {
    const res = await apiClient.get("/analytics/chitti/transactions", { params });
    return { data: res.data.data, meta: res.data.meta };
  },
};
