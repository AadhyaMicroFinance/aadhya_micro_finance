import apiClient, { API_BASE } from "./api-client";
import {
  AGREEMENT_CONFIRMATION_TEXT,
  type ApiResponse,
  type FinanceAccount,
  type FinanceAccountCreateRequest,
  type FinanceAgreement,
  type FinanceAgreementConfirmation,
  type FinanceAgreementCreate,
  type FinanceAgreementPrint,
  type FinanceCollectionRecord,
  type FinanceCollectionsParams,
  type FinanceDashboardData,
  type FinancePendingCollectionRecord,
  type FinanceSchedule,
} from "@/types";

export { AGREEMENT_CONFIRMATION_TEXT };

const agreementDownloadPath = (agreementId: string): string =>
  `${API_BASE}/finance/agreements/${encodeURIComponent(agreementId)}/download`;

export const financeApi = {
  list: async (params: {
    page?: number;
    per_page?: number;
    status?: string;
    customer_id?: string;
    search?: string;
    agreement_status?: string;
  } = {}) => {
    const res = await apiClient.get<ApiResponse<FinanceAccount[]>>("/finance", { params });
    return res.data;
  },

  /** Finance-only dashboard KPIs, trends and activity feeds. */
  dashboard: async (): Promise<FinanceDashboardData> => {
    const res = await apiClient.get<ApiResponse<FinanceDashboardData>>("/finance/dashboard");
    return res.data.data;
  },

  /** Paginated Finance repayment history. Finance rows only. */
  collections: async (params: FinanceCollectionsParams = {}) => {
    const { date_from, date_to, ...rest } = params;
    const res = await apiClient.get<ApiResponse<FinanceCollectionRecord[]>>(
      "/finance/collections",
      {
        params: {
          ...rest,
          date_from,
          date_to,
          // Accept either date parameter convention used by the API layer.
          start_date: date_from,
          end_date: date_to,
        },
      }
    );
    return res.data;
  },

  /** Pending and overdue Finance installments (never Chitti contributions). */
  pendingCollections: async (): Promise<FinancePendingCollectionRecord[]> => {
    const res = await apiClient.get<ApiResponse<FinancePendingCollectionRecord[]>>(
      "/finance/collections/pending"
    );
    return res.data.data;
  },

  get: async (id: string): Promise<FinanceAccount> => {
    const res = await apiClient.get<ApiResponse<FinanceAccount>>(`/finance/${id}`);
    return res.data.data;
  },

  create: async (data: FinanceAccountCreateRequest): Promise<FinanceAccount> => {
    const res = await apiClient.post<ApiResponse<FinanceAccount>>("/finance", data);
    return res.data.data;
  },

  getSchedule: async (id: string): Promise<FinanceSchedule[]> => {
    const res = await apiClient.get<ApiResponse<FinanceSchedule[]>>(`/finance/${id}/schedule`);
    return res.data.data;
  },

  update: async (id: string, data: { status?: string; notes?: string | null }): Promise<FinanceAccount> => {
    const res = await apiClient.put<ApiResponse<FinanceAccount>>(`/finance/${id}`, data);
    return res.data.data;
  },

  // ---- Agreements ----

  generateAgreement: async (data: FinanceAgreementCreate): Promise<FinanceAgreement> => {
    const res = await apiClient.post<ApiResponse<FinanceAgreement>>(
      "/finance/agreements/generate",
      data
    );
    return res.data.data;
  },

  getAgreement: async (agreementId: string): Promise<FinanceAgreement> => {
    const res = await apiClient.get<ApiResponse<FinanceAgreement>>(
      `/finance/agreements/${encodeURIComponent(agreementId)}`
    );
    return res.data.data;
  },

  printAgreement: async (agreementId: string): Promise<FinanceAgreementPrint> => {
    const res = await apiClient.post<ApiResponse<FinanceAgreementPrint>>(
      `/finance/agreements/${encodeURIComponent(agreementId)}/print`
    );
    return res.data.data;
  },

  /** Download URL for the server-rendered agreement document. */
  downloadAgreement: agreementDownloadPath,
  agreementDownloadUrl: agreementDownloadPath,

  confirmAgreement: async (
    agreementId: string,
    confirmationText: string = AGREEMENT_CONFIRMATION_TEXT
  ): Promise<FinanceAgreementConfirmation> => {
    const res = await apiClient.post<ApiResponse<FinanceAgreementConfirmation>>(
      `/finance/agreements/${encodeURIComponent(agreementId)}/confirm`,
      { confirmation_text: confirmationText }
    );
    return res.data.data;
  },
};
