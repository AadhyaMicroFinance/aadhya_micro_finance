/**
 * Centralized API client with auth interceptors.
 * All API calls go through this client.
 */

import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

/**
 * Unauthenticated client for auth bootstrap calls.
 *
 * Login/refresh must not run through the authenticated client below: a stale
 * access or refresh token in localStorage must never block, retry, or redirect
 * a fresh sign-in attempt. The timeout guarantees a hung auth request cannot
 * leave the Sign In button spinning forever.
 */
export const publicApiClient = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
  timeout: 20000,
});

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

function isAuthEndpoint(url?: string): boolean {
  return !!url && /\/auth\/(login|refresh)(?:\?|$)/.test(url);
}

function isLoginPage(): boolean {
  return typeof window !== "undefined" && window.location.pathname === "/login";
}

function clearStoredTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

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
  if (typeof window !== "undefined" && !isAuthEndpoint(config.url)) {
    const token = localStorage.getItem("access_token");
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Response interceptor: handle 401, try refresh once, then surface the error.
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;

    if (
      error.response?.status !== 401 ||
      !originalRequest ||
      originalRequest._retry ||
      isAuthEndpoint(originalRequest.url)
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    if (typeof window === "undefined") {
      return Promise.reject(error);
    }

    // A 401 while signing in must be shown on the login page, not cause a
    // same-page reload that discards the error and strands the loading state.
    if (isLoginPage()) {
      clearStoredTokens();
      return Promise.reject(error);
    }

    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) {
      clearStoredTokens();
      window.location.href = "/login";
      return Promise.reject(error);
    }

    try {
      const res = await publicApiClient.post<{
        data: { access_token: string; refresh_token: string };
      }>("/auth/refresh", { refresh_token: refreshToken });
      const { access_token, refresh_token } = res.data.data;
      localStorage.setItem("access_token", access_token);
      localStorage.setItem("refresh_token", refresh_token);
      originalRequest.headers = originalRequest.headers ?? {};
      originalRequest.headers.Authorization = `Bearer ${access_token}`;
      return apiClient(originalRequest);
    } catch {
      clearStoredTokens();
      window.location.href = "/login";
      return Promise.reject(error);
    }
  }
);

export default apiClient;
