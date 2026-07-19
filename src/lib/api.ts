// Shared API client for the external VeraMove FastAPI backend.
// Frontend-only: do not add any server-side logic here.

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

// ---------- Types (mirror backend contract) ----------

export type JobState =
  | "draft"
  | "intake_complete"
  | "confirmed"
  | "calling"
  | "quotes_ready"
  | "negotiating"
  | "completed"
  | "failed";

export interface LocationSpec {
  address_summary: string;
  dwelling_type: string;
  floors: number;
  stairs: number;
  elevator_access: boolean;
  parking_distance_feet: number;
  access_notes?: string;
}


export interface InventoryItem {
  item_id: string;
  name: string;
  quantity: number;
  room: string;
  oversized: boolean;
  fragile: boolean;
  notes?: string;
}

export interface ServicesSpec {
  packing: boolean;
  disassembly: boolean;
  storage: boolean;
  storage_days?: number;
}

export interface SourceContext {
  intake_method: "voice" | "document" | string;
  vera_user_id?: string;
  vera_property_id?: string;
}

export interface JobSpecV1 {
  job_id: string;
  version: "1.0";

  move_date: string;
  date_flexible: boolean;
  origin: LocationSpec;
  destination: LocationSpec;
  bedroom_count: number;
  inventory: InventoryItem[];
  oversized_or_fragile_items?: string[];
  services?: ServicesSpec;
  insurance_preference: string;
  confirmed: boolean;
  confirmed_at?: string | null;
  source_context?: SourceContext;
}

export interface FeeLineItem {
  description: string;
  amount: string;
  category: string;
  disclosed_upfront: boolean;
}


export interface QuoteV1 {
  quote_id: string;
  job_id: string;
  job_spec_version: "1.0";
  vendor: { vendor_id: string; name: string };
  currency: string;
  original_total: string;
  negotiated_total: string;
  deposit: string;
  binding_type: "binding" | "non_binding";
  availability: string;
  verification_status: "verified" | "partially_verified" | "unverified";
  concessions?: string[];
  fee_line_items: FeeLineItem[];

  red_flags?: string[];
  recording_url?: string;
  transcript_evidence?: string;
}

export type CallOutcomeType =
  | "itemized_quote"
  | "callback_commitment"
  | "documented_decline"
  | "failed";

export interface CallOutcome {
  type: CallOutcomeType;
  summary?: string;
  notes?: string;
}

export interface CallRecord {
  call_id: string;
  job_id: string;
  vendor_id: string;
  vendor_name?: string;
  recording_url?: string;
  transcript?: string;
  outcome: CallOutcome;
  created_at: string;
  updated_at: string;
}


export interface RecommendationRanking {
  quote_id: string;
  rank: number;
  vendor: { vendor_id: string; name: string };
  total: string;
  rationale: string[];
  red_flags?: string[];
  evidence_ids: string[];
}


export interface TranscriptEvidence {
  evidence_id: string;
  claim: string;
  recording_url: string;
}

export interface RecommendationV1 {
  recommendation_id: string;
  summary: string;
  winning_vendor_id: string;
  rankings: RecommendationRanking[];
  transcript_evidence: TranscriptEvidence[];
  version: number;
}

export interface JobRecord {
  job_spec: JobSpecV1;
  state: JobState;
  calls: unknown[];
  quotes: QuoteV1[];
  recommendation: RecommendationV1 | null;
  created_at: string;
  updated_at: string;
}

// ---------- Client ----------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${res.statusText} at ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; mode: string; service: string }>("/health"),
  createJob: (spec: JobSpecV1) =>
    request<JobRecord>("/api/jobs", { method: "POST", body: JSON.stringify(spec) }),
  getJob: (jobId: string) => request<JobRecord>(`/api/jobs/${jobId}`),
  confirmJob: (jobId: string) =>
    request<JobRecord>(`/api/jobs/${jobId}/confirm`, { method: "POST" }),
  createCalls: (jobId: string) =>
    request<JobRecord>(`/api/jobs/${jobId}/calls`, { method: "POST" }),
  negotiate: (jobId: string) =>
    request<JobRecord>(`/api/jobs/${jobId}/negotiate`, { method: "POST" }),
  getReport: (jobId: string) => request<RecommendationV1>(`/api/jobs/${jobId}/report`),
  discoverVendors: () => request<unknown>("/api/vendors/discover"),
};

export function formatCurrency(amount: string, currency = "USD"): string {
  const n = Number.parseFloat(amount);
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(n);
  } catch {
    return `$${n.toFixed(2)}`;
  }
}

