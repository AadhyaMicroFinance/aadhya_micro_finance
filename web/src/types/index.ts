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
  }[];
  payment_history: {
    id: string;
    transaction_id: string;
    amount: number;
    payment_method: string;
    payment_date: string;
    status: string;
  }[];
}

// ==========================================
// Finance Types
// ==========================================

export interface FinanceAccount {
  id: string;
  account_number: string;
  customer_id: string;
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
  finance_account_id: string | null;
  chitti_account_id: string | null;
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
