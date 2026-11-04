import apiClient from "./api-client";
import type { ApiResponse, LoginRequest, TokenResponse, MeResponse } from "@/types";

export const authApi = {
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const res = await apiClient.post<ApiResponse<TokenResponse>>("/auth/login", data);
    return res.data.data;
  },

  getMe: async (): Promise<MeResponse> => {
    const res = await apiClient.get<ApiResponse<MeResponse>>("/auth/me");
    return res.data.data;
  },

  refresh: async (refreshToken: string): Promise<TokenResponse> => {
    const res = await apiClient.post<ApiResponse<TokenResponse>>("/auth/refresh", {
      refresh_token: refreshToken,
    });
    return res.data.data;
  },
};
