import apiClient from "./api-client";
import type { ApiResponse, Payment, DueInfo } from "@/types";

export const paymentsApi = {
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
