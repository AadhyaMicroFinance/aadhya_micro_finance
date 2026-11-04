import apiClient from "./api-client";
import type { ApiResponse, User } from "@/types";

export const usersApi = {
  list: async (params: { page?: number; per_page?: number; role?: string }) => {
    const res = await apiClient.get<ApiResponse<User[]>>("/users", { params });
    return res.data;
  },

  get: async (id: string): Promise<User> => {
    const res = await apiClient.get<ApiResponse<User>>(`/users/${id}`);
    return res.data.data;
  },

  create: async (data: { username: string; email: string; password: string; full_name: string; role: string }) => {
    const res = await apiClient.post<ApiResponse<User>>("/users", data);
    return res.data.data;
  },

  update: async (id: string, data: Partial<User>) => {
    const res = await apiClient.put<ApiResponse<User>>(`/users/${id}`, data);
    return res.data.data;
  },

  deactivate: async (id: string) => {
    const res = await apiClient.delete<ApiResponse<unknown>>(`/users/${id}`);
    return res.data;
  },
};
