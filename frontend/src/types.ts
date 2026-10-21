export type Role = "CLIENT" | "EMPLOYEE";
export interface User {
  id: number;
  login: string;
  first_name: string;
  full_name: string;
  role: Role;
}
export interface Company {
  id: number;
  name: string;
  legal_form: "IP" | "OOO";
  legal_form_label: string;
  registration_label: string;
  registration_number: string;
  max_amount: number;
}
export interface Rating {
  score: number;
  max: number;
  band: string;
  band_label: string;
  source_label: string;
  updated_at: string;
  hint: string;
}
export interface Loan {
  id: number;
  name: string;
  balance: number;
  original_amount: number;
  rate: number;
  next_payment_date: string;
  next_payment_amount: number;
  active_application_id?: number | null;
}
export interface Profile {
  industry?: string | null;
  months_operating?: number | null;
  monthly_revenue?: number | null;
  monthly_debt_payments?: number | null;
  purpose_details?: string | null;
}
export type ProfileKey = keyof Profile;
export interface ProfileField {
  key: ProfileKey;
  label: string;
  label_refinance?: string;
  type: "string" | "integer";
  unit: string | null;
  hint: string;
}
export type Status =
  | "DRAFT"
  | "IN_REVIEW"
  | "NEED_INFO"
  | "APPROVED"
  | "COUNTER_OFFER"
  | "REJECTED"
  | "COMPLETED";
export type Mode = "NEW_CREDIT" | "REFINANCE";
export interface Brief {
  id: number;
  number: string | null;
  company_id: number;
  company_name: string;
  borrowing_mode: Mode;
  borrowing_mode_label: string;
  product_id: string | null;
  product_name: string | null;
  existing_loan_name: string | null;
  amount: number | null;
  term_months: number | null;
  status: Status;
  status_label: string;
  current_step: string | null;
  created_at: string;
  submitted_at: string | null;
  client_name?: string;
}
export interface Terms {
  amount: number;
  term_months: number;
  rate: number;
  monthly_payment: number;
}
export interface Decision extends Terms {
  id: number;
  kind: string;
  kind_label: string;
  comment: string | null;
  reason_text: string | null;
  requested: Terms;
  changed_fields: string[];
  refinance_remainder_text: string | null;
  created_at: string;
}
export interface AppEvent {
  id: number;
  label: string;
  actor: string;
  created_at: string;
  text: string | null;
  fields: Partial<Profile> | null;
}
export interface Application extends Brief {
  client?: { full_name: string };
  company: Company;
  existing_loan: Loan | null;
  preliminary_rate: number | null;
  preliminary_payment: number | null;
  rating_note: string | null;
  preliminary_note: string;
  business_profile: Profile;
  comparison: {
    current_rate: number;
    new_rate: number;
    current_next_payment: number;
    new_payment: number;
    is_better: boolean;
    note: string;
  } | null;
  next_steps_text: string;
  stage: { steps: { key: string; label: string; state: string }[] };
  decided_at: string | null;
  completed_at: string | null;
  info_request: {
    id: number;
    message: string;
    requested_fields: { key: ProfileKey; label: string }[];
  } | null;
  decision: Decision | null;
  events: AppEvent[];
  available_actions: string[];
  rating?: Rating | null;
  scoring?: {
    recommendation: string;
    recommendation_label: string;
    debt_load_pct: number | null;
    reasons: string[];
  };
  checks?: { key: string; label: string; status: string; details: string }[];
  staff_actions?: string[];
  info_requests?: {
    id: number;
    message: string;
    requested_fields: ProfileKey[];
    answer_text: string | null;
    answer_fields: Profile;
    created_by: string;
    answered_at: string | null;
  }[];
}
export interface News {
  id: number;
  tag: string;
  title: string;
  summary: string;
  body?: string;
}
export interface Dashboard {
  company: Company;
  client: { full_name: string };
  rating: Rating | null;
  rating_unavailable_text: string;
  loans: Loan[];
  active_applications: Brief[];
  past_applications: Brief[];
  news: News[];
}
export interface Config {
  amount: {
    min: number;
    step: number;
    max_by_legal_form: Record<string, number>;
    default: number;
  };
  term: { min: number; max: number; step: number; default: number };
  products: {
    product_id: string;
    name: string;
    card_title: string;
    description: string;
  }[];
  borrowing_modes: {
    borrowing_mode: Mode;
    button_label: string;
    name: string;
  }[];
  legal_forms: {
    legal_form: "IP" | "OOO";
    label: string;
    registration_label: string;
    registration_length: number;
  }[];
  profile_fields: ProfileField[];
  texts: Record<string, string>;
}
