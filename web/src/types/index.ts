// ==========================================
// API Response Types
// ==========================================

export interface ApiResponse<T = unknown> {
  success: boolean;
  data: T;
  error: { code: string; message: string } | null;
  meta: {
    page: number;
    per_page: number;
    total: number;
    total_pages: number;
  } | null;
}

// ==========================================
// Auth Types
// ==========================================

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface MeResponse {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: string;
  permissions: string[];
}

// ==========================================
// Customer Types
// ==========================================

export interface Customer {
  id: string;
  customer_code: string;
  full_name: string;
  date_of_birth: string | null;
  gender: string | null;
  mobile_number: string;
  alternate_mobile: string | null;
  email: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
  pan_number: string | null;
  aadhar_number: string | null;
  occupation: string | null;
  nominee_name: string | null;
  nominee_phone: string | null;
  nominee_relation: string | null;
  notes: string | null;
  status: "ACTIVE" | "INACTIVE" | "BLOCKED";
  created_at: string;
  updated_at: string;
}

export interface CustomerLedger {
  customer: {
    id: string;
    customer_code: string;
    full_name: string;
    mobile_number: string;
  };
  finance_accounts: {
    id: string;
    account_number: string;
    total_payable: number;
    status: string;
  }[];
  chitti_groups: {
    id: string;
    group_code: string;
    group_name: string;
    status: string;
  }[];
  chittis: {
    id: string;
    chitti_code: string;
    name: string;
    status: string;
    member_id: string;
    member_number: number;
    payout_order: number | null;
    alias: string | null;
    slot_status: string;
    total_paid: number;
    outstanding: number;
    agreement_status: string;
    agreement_number: string | null;
    lift_status: string;
  }[];
  payment_history: {
    id: string;
    transaction_id: string;
    source: "FINANCE" | "CHITTI";
    customer_name: string;
    account_name: string | null;
    member_id: string | null;
    member_number: number | null;
    alias: string | null;
    period_number: number | null;
    amount: number;
    payment_method: string | null;
    payment_date: string | null;
    event_type: string | null;
    status: string;
    is_reversal: boolean;
    reversal_of_transaction_id: string | null;
    reversed_by_transaction_id: string | null;
  }[];
  payment_summary: {
    transaction_count: number;
    successful_transaction_count: number;
    successful_paid_total: number;
  };
}

// ==========================================
// Finance Types
// ==========================================

export interface FinanceAccount {
  id: string;
  account_number: string;
  customer_id: string;
  customer_name?: string | null;
  customer_code?: string | null;
  mobile_number?: string | null;
  principal_amount: number;
  interest_rate: number;
  interest_type: string;
  fees: number;
  total_payable: number;
  installment_amount: number;
  frequency: string;
  start_date: string;
  first_due_date: string;
  number_of_installments: number;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface FinanceSchedule {
  id: string;
  installment_number: number;
  due_date: string;
  expected_amount: number;
  paid_amount: number;
  remaining_amount: number;
  status: string;
}

/**
 * Exact wording the Finance agreement API requires for a signing confirmation.
 * Kept here (and re-exported from `@/services/finance`) so every caller uses one
 * source of truth.
 */
export const AGREEMENT_CONFIRMATION_TEXT =
  "I confirm that the agreement has been signed by the customer.";

/** Finance account row returned by the list endpoint, including agreement state. */
export type FinanceAccountListItem = FinanceAccount & {
  agreement_status?: string;
};

export interface FinanceDashboardKpis {
  total_accounts: number;
  total_principal_disbursed: number;
  total_outstanding: number;
  total_collections: number;
  pending_repayments: number;
  overdue_repayments: number;
}

export interface FinanceTrendPoint {
  period: string;
  expected: number;
  collected: number;
}

export interface FinanceStatusCount {
  status: string;
  count: number;
}

/**
 * Dashboard feed items can be produced by several ledger events. The known
 * fields are typed; the index signature keeps the renderer tolerant of extra
 * metadata added by the backend later.
 */
export interface FinanceActivityItem {
  id?: string | null;
  transaction_id?: string | null;
  customer_name?: string | null;
  account_number?: string | null;
  activity_type?: string | null;
  event_type?: string | null;
  description?: string | null;
  amount?: number | null;
  status?: string | null;
  date?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface FinanceRepaymentItem {
  id?: string | null;
  schedule_id?: string | null;
  finance_account_id?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  account_number?: string | null;
  installment_number?: number | null;
  due_date?: string | null;
  expected_amount?: number | null;
  remaining_amount?: number | null;
  pending_amount?: number | null;
  status?: string | null;
  [key: string]: unknown;
}

export interface FinanceOverdueAccount {
  id?: string | null;
  finance_account_id?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  account_number?: string | null;
  days_overdue?: number | null;
  overdue_amount?: number | null;
  outstanding_amount?: number | null;
  status?: string | null;
  [key: string]: unknown;
}

export interface FinanceDashboardData {
  kpis: FinanceDashboardKpis;
  trends: FinanceTrendPoint[];
  status_distribution: FinanceStatusCount[];
  recent_activity: FinanceActivityItem[];
  upcoming_repayments: FinanceRepaymentItem[];
  overdue_accounts: FinanceOverdueAccount[];
}

/** A single Finance repayment collection (never a Chitti contribution). */
export interface FinanceCollectionRecord {
  id: string;
  transaction_id: string;
  customer_id: string;
  customer_name: string;
  finance_account_id: string;
  account_number: string;
  installment_number: number;
  amount: number;
  payment_method: string;
  payment_date: string;
  status: string;
  is_reversal: boolean;
  collected_by: string | null;
  created_at: string;
}

/** Pending/overdue Finance installment returned by `/finance/collections/pending`. */
export interface FinancePendingCollectionRecord {
  id?: string | null;
  schedule_id?: string | null;
  finance_schedule_id?: string | null;
  finance_account_id?: string | null;
  account_id?: string | null;
  account_number?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  mobile_number?: string | null;
  installment_number?: number | null;
  due_date?: string | null;
  expected_amount?: number | null;
  remaining_amount?: number | null;
  pending_amount?: number | null;
  outstanding_amount?: number | null;
  amount_due?: number | null;
  days_overdue?: number | null;
  status?: string | null;
  source?: string | null;
  [key: string]: unknown;
}

export interface FinanceCollectionsParams {
  page?: number;
  per_page?: number;
  search?: string;
  date_from?: string;
  date_to?: string;
  status?: string;
}

export interface FinanceAgreementCreate {
  customer_id: string;
  principal_amount: number;
  interest_rate: number;
  interest_type: string;
  fees: number;
  frequency: string;
  start_date: string;
  first_due_date: string;
  number_of_installments: number;
}

/** Payload accepted by `financeApi.create` once an agreement is confirmed. */
export interface FinanceAccountCreateRequest extends FinanceAgreementCreate {
  agreement_id: string;
  custom_installment_amount?: number;
  notes?: string;
}

export interface FinanceAgreementScheduleItem {
  installment_number: number;
  due_date: string;
  expected_amount: number;
}

export interface FinanceAgreement {
  agreement_id: string;
  agreement_number: string;
  agreement_html?: string;
  agreement_text?: string;
  customer_id?: string | null;
  customer_name: string;
  customer_code: string;
  mobile_number: string;
  terms: Record<string, unknown>;
  schedule: FinanceAgreementScheduleItem[];
  generated_at: string;
  status: string;
  agreement_status?: string;
  print_count?: number;
  printed_at?: string;
  confirmed_at?: string | null;
  confirmed_by?: string | null;
  [key: string]: unknown;
}

export interface FinanceAgreementPrint {
  agreement_id: string;
  agreement_html?: string;
  agreement_text?: string;
  print_count?: number;
  printed_at?: string;
  status: string;
}

export interface FinanceAgreementConfirmation {
  agreement_id: string;
  status: string;
  confirmed_at: string | null;
  confirmed_by: string | null;
}

// ==========================================
// Chitti Types
// ==========================================

export interface ChittiGroup {
  id: string;
  group_code: string;
  customer_id: string;
  group_name: string;
  chitti_type: string;
  chitti_amount: number;
  number_of_members: number;
  installment_amount: number;
  frequency: string;
  start_date: string;
  end_date: string;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// ==========================================
// Payment Types
// ==========================================

export interface Payment {
  id: string;
  transaction_id: string;
  customer_id: string;
  customer_name?: string | null;
  finance_account_id: string | null;
  finance_schedule_id?: string | null;
  installment_number?: number | null;
  chitti_account_id: string | null;
  member_id?: string | null;
  member_number?: number | null;
  member_alias?: string | null;
  member_name?: string | null;
  chitti_name?: string | null;
  period_number?: number | null;
  account_type?: "FINANCE" | "CHITTI";
  transaction_type?: string;
  amount: number;
  payment_method: string;
  payment_date: string;
  reference_number: string | null;
  notes: string | null;
  is_reversal: boolean;
  status: string;
  collected_by: string | null;
  created_at: string;
}

export interface DueInfo {
  account_id: string;
  account_number: string;
  account_type: string;
  amount_due: number;
  outstanding: number;
  next_due_date: string | null;
  next_installment_number: number | null;
  total_paid: number;
  total_payable: number;
}

// ==========================================
// User Types
// ==========================================

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

// ==========================================
// Administration Types
// ==========================================

export interface EffectiveSettings {
  business_timezone: string;
  advance_payment_policy: "EXPLICIT_CREDIT_ONLY";
  notification_delivery_enabled: boolean;
  whatsapp_configured: boolean;
  saved_settings: Array<{
    key: string;
    value: unknown;
    description: string | null;
    updated_at: string | null;
  }>;
}

export interface AuditLogEntry {
  id: string;
  created_at: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
}

export interface WhatsAppMessageLogEntry {
  id: string;
  customer_name: string;
  phone_number: string;
  template_name: string;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface WhatsAppStatus {
  configured: boolean;
  stats: {
    sent_today: number;
    failed_today: number;
    delivery_rate: number | null;
  };
  messages: WhatsAppMessageLogEntry[];
}
