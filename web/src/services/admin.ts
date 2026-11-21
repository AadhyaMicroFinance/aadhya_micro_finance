import apiClient from "./api-client";
import type {
  ApiResponse,
  AuditLogEntry,
  EffectiveSettings,
  WhatsAppStatus,
} from "@/types";

export interface AuditQuery {
  date_from?: string;
  date_to?: string;
  action?: string;
  entity_type?: string;
  page?: number;
  per_page?: number;
}

export const adminApi = {
  settings: async (): Promise<EffectiveSettings> => {
    const res = await apiClient.get<ApiResponse<EffectiveSettings>>("/admin/settings");
    return res.data.data;
  },

  audit: async (params: AuditQuery) => {
    const res = await apiClient.get<
      ApiResponse<AuditLogEntry[]> & { meta: { total: number; total_pages: number } }
    >("/admin/audit", { params });
    return res.data;
  },

  whatsapp: async (): Promise<WhatsAppStatus> => {
    const res = await apiClient.get<ApiResponse<WhatsAppStatus>>("/admin/whatsapp");
    return res.data.data;
  },
};
