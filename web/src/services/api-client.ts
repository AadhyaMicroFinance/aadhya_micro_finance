/**
 * Centralized API client with auth interceptors.
 * All API calls go through this client.
 */

import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

interface ApiErrorBody {
  success?: boolean;
  error?: { code?: string; message?: string; details?: unknown };
}

/**
 * Extract the backend's human-readable error message.
 *
 * Without this, a 409/400 surfaces as "Request failed with status code 409"
 * even though the API sent a specific explanation.
 */
export function getApiErrorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  const body = (error as AxiosError<ApiErrorBody>)?.response?.data;
  const message = body?.error?.message;
  if (typeof message === "string" && message.trim().length > 0) return message;
  if (error instanceof Error && error.message && !/^Request failed with status code/.test(error.message)) {
    return error.message;
  }
  return fallback;
}

/** Structured `error.details` payload (blockers, duplicate info, ...). */
export function getApiErrorDetails<T>(error: unknown): T | null {
  const body = (error as AxiosError<ApiErrorBody>)?.response?.data;
  const details = body?.error?.details;
  return details && typeof details === "object" ? (details as T) : null;
}

/** HTTP status of a failed request, or null when the request never completed. */
export function getApiErrorStatus(error: unknown): number | null {
  return (error as AxiosError)?.response?.status ?? null;
}

// Request interceptor: attach access token
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Response interceptor: handle 401, try refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      if (typeof window !== "undefined") {
        const refreshToken = localStorage.getItem("refresh_token");
        if (refreshToken) {
          try {
            const res = await axios.post(`${API_BASE}/auth/refresh`, {
              refresh_token: refreshToken,
            });
            const { access_token, refresh_token } = res.data.data;
            localStorage.setItem("access_token", access_token);
            localStorage.setItem("refresh_token", refresh_token);
            originalRequest.headers.Authorization = `Bearer ${access_token}`;
            return apiClient(originalRequest);
          } catch {
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");
            window.location.href = "/login";
          }
        } else {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
