import apiClient from "./api-client";
import type { ApiResponse, Customer, CustomerLedger } from "@/types";

export const customersApi = {
  list: async (params: { page?: number; per_page?: number; search?: string; status?: string }) => {
    const res = await apiClient.get<ApiResponse<Customer[]>>("/customers", { params });
    return res.data;
  },

  get: async (id: string): Promise<Customer> => {
    const res = await apiClient.get<ApiResponse<Customer>>(`/customers/${id}`);
    return res.data.data;
  },

  create: async (data: Partial<Customer> & { full_name: string; mobile_number: string }) => {
    const res = await apiClient.post<ApiResponse<Customer>>("/customers", data);
    return res.data.data;
  },

  update: async (id: string, data: Partial<Customer>) => {
    const res = await apiClient.put<ApiResponse<Customer>>(`/customers/${id}`, data);
    return res.data.data;
  },

  getLedger: async (id: string): Promise<CustomerLedger> => {
    const res = await apiClient.get<ApiResponse<CustomerLedger>>(`/customers/${id}/ledger`);
    return res.data.data;
  },
};
