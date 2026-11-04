import apiClient from "./api-client";
import type { ApiResponse, FinanceAccount, FinanceSchedule } from "@/types";

export const financeApi = {
  list: async (params: { page?: number; per_page?: number; status?: string; customer_id?: string }) => {
    const res = await apiClient.get<ApiResponse<FinanceAccount[]>>("/finance", { params });
    return res.data;
  },

  get: async (id: string): Promise<FinanceAccount> => {
    const res = await apiClient.get<ApiResponse<FinanceAccount>>(`/finance/${id}`);
    return res.data.data;
  },

  create: async (data: {
    customer_id: string;
    principal_amount: number;
    interest_rate?: number;
    interest_type?: string;
    fees?: number;
    frequency: string;
    start_date: string;
    first_due_date: string;
    number_of_installments: number;
    custom_installment_amount?: number;
    notes?: string;
  }) => {
    const res = await apiClient.post<ApiResponse<FinanceAccount>>("/finance", data);
    return res.data.data;
  },

  getSchedule: async (id: string): Promise<FinanceSchedule[]> => {
    const res = await apiClient.get<ApiResponse<FinanceSchedule[]>>(`/finance/${id}/schedule`);
    return res.data.data;
  },
};
