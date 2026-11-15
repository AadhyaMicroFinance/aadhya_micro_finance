import apiClient from "./api-client";
import type { ApiResponse, Payment, DueInfo } from "@/types";

export interface PendingPaymentRecord {
  id: string;
  source: "FINANCE" | "CHITTI";
  customer_id: string;
  customer_code: string;
  customer_name: string;
  mobile_number: string;
  account_id: string;
  account_name: string;
  account_code: string;
  schedule_id: string | null;
  member_id: string | null;
  period_number: number;
  due_date: string;
  expected_amount: number;
  outstanding_amount: number;
  status: string;
}

export const paymentsApi = {
  pending: async (): Promise<PendingPaymentRecord[]> => {
    const res = await apiClient.get<ApiResponse<PendingPaymentRecord[]>>("/payments/pending");
    return res.data.data;
  },

  eligibleAccounts: async (customerId: string) => {
    const res = await apiClient.get<ApiResponse<{
      finance_accounts: Array<{ id: string; account_number: string; installment_amount: number; frequency: string; status: string }>;
      chitti_memberships: Array<{ chitti_id: string; chitti_code: string; chitti_name: string; member_id: string; member_number: number; total_value: number; frequency: string; current_period: number; due_date: string | null; amount_due: number; outstanding: number; status: string }>;
    }>>(`/payments/customer/${customerId}/eligible-accounts`);
    return res.data.data;
  },
  list: async (params: { page?: number; per_page?: number; customer_id?: string }) => {
    const res = await apiClient.get<ApiResponse<Payment[]>>("/payments", { params });
    return res.data;
  },

  create: async (data: {
    customer_id: string;
    finance_account_id?: string;
    chitti_account_id?: string;
    finance_schedule_id?: string;
    amount: number;
    payment_method: string;
    payment_date: string;
    reference_number?: string;
    notes?: string;
    idempotency_key: string;
  }) => {
    const res = await apiClient.post<ApiResponse<Payment>>("/payments", data);
    return res.data.data;
  },

  reverse: async (id: string, reason: string) => {
    const res = await apiClient.post<ApiResponse<Payment>>(`/payments/${id}/reverse`, {
      reversal_reason: reason,
    });
    return res.data.data;
  },

  getDue: async (customerId: string, financeAccountId: string): Promise<DueInfo> => {
    const res = await apiClient.get<ApiResponse<DueInfo>>(`/payments/due/${customerId}`, {
      params: { finance_account_id: financeAccountId },
    });
    return res.data.data;
  },
};
