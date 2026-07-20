import type { components } from "@/api/schema";

// These are presentation-only shapes used by the imported Lovable screens.
// Canonical API/domain contracts come exclusively from src/api/schema.d.ts;
// live responses are converted into these shapes in adapters.ts.
type Schemas = components["schemas"];

export type JobViewState = Schemas["JobState"];
export type CallViewStatus = Schemas["CallStatus"] | "queued" | "dialing" | "negotiating";
export type CallViewOutcome = Schemas["CallOutcomeType"];

export type RequirementId =
  | "ai_disclosure"
  | "friction_handled"
  | "verified_leverage"
  | "structured_ending";

export type RequirementState = "passed" | "failed" | "pending";

export interface EvidenceView {
  callId: string;
  ts: string;
  excerpt: string;
}

export interface RequirementView {
  id: RequirementId;
  label: string;
  state: RequirementState;
  evidence?: EvidenceView;
}

export interface FeeItemView {
  label: string;
  amount: number;
  note?: string;
  revealedAfterQuestioning?: boolean;
}

export interface RedFlagView {
  id: string;
  severity: "risk" | "caution";
  message: string;
  evidence?: EvidenceView;
}

export interface TranscriptLineView {
  ts: string;
  speaker: "agent" | "vendor" | "system";
  text: string;
  tag?: "hidden_fee" | "leverage" | "disclosure" | "commitment" | "decline";
}

export interface RecordingView {
  url: string;
  durationSec: number;
}

export interface NegotiationView {
  beforeTotal: number;
  afterTotal: number;
  delta: number;
  leverageVendorId: string;
  addedInclusions: string[];
}

export interface VendorView {
  id: string;
  name: string;
  kind: "transparent" | "budget" | "premium";
}

export interface CallView {
  id: string;
  jobId: string;
  vendor: VendorView;
  status: CallViewStatus;
  outcome?: CallViewOutcome;
  headlineQuote?: number;
  verifiedTotal?: number;
  binding: boolean;
  fees: FeeItemView[];
  hiddenFees: FeeItemView[];
  redFlags: RedFlagView[];
  requirements: RequirementView[];
  transcript: TranscriptLineView[];
  recording?: RecordingView;
  negotiation?: NegotiationView;
  startedAt?: string;
  endedAt?: string;
}

export interface MoveDetailsView {
  originCity: string;
  originState: string;
  destinationCity: string;
  destinationState: string;
  date: string;
  flexibilityDays: number;
}

export interface AccessDetailsView {
  originFloor: number;
  originStairs: number;
  originElevator: boolean;
  destinationFloor: number;
  destinationStairs: number;
  destinationElevator: boolean;
  longCarryFt: number;
  destinationLongCarryFt: number;
}

export interface InventoryItemView {
  item: string;
  qty: number;
  notes?: string;
}

export interface ServiceDetailsView {
  packing: boolean;
  insuranceTier: "standard" | "full-value";
}

export interface ExtrasDetailsView {
  disassembly: boolean;
  storage: boolean;
  oversizedOrFragile: string[];
}

export type ExtractionSource = "voice" | "document" | "manual";

export interface JobView {
  id: string;
  version: number;
  status: JobViewState;
  synthetic: boolean;
  homeType: string;
  bedrooms?: number;
  move: MoveDetailsView;
  access: AccessDetailsView;
  inventory: InventoryItemView[];
  services: ServiceDetailsView;
  extras?: ExtrasDetailsView;
  notes?: string;
  missingFields: string[];
  fieldWarnings?: Record<string, string>;
  editedFields?: string[];
  extractionSource?: ExtractionSource;
  createdAt: string;
  confirmedAt?: string;
}

export type VerificationState =
  | Schemas["VerificationStatus"]
  | "role_play"
  | "failed";

export type CompletenessState = "complete" | "partial" | "incomplete";

export interface RankedVendorView {
  vendorId: string;
  vendorName: string;
  score?: number;
  finalTotal?: number;
  binding: boolean;
  reasons: string[];
  label?: string;
  headlineTotal?: number;
  verifiedTotal?: number;
  negotiatedTotal?: number;
  verificationState?: VerificationState;
  availability?: string;
  deposit?: number;
  concessions?: string[];
  hiddenFeeCount?: number;
  redFlagCount?: number;
  evidenceCount?: number;
  hasRecording?: boolean;
  completeness?: CompletenessState;
  warnings?: string[];
  synthetic?: boolean;
}

export interface ReportNarrativeView {
  whyThisVendor?: string;
  whyNotCheapest?: string;
  whatChanged?: string;
  remainingUncertainty?: string;
  whatToVerify?: string;
}

export interface ReportView {
  jobId: string;
  ranking: RankedVendorView[];
  recommended: {
    vendorId: string;
    label: string;
    tradeoffs: string[];
    savingsVsHighest: number;
  };
  medianVerifiedTotal?: number;
  evidenceIndex: Array<{
    callId: string;
    vendorName: string;
    note: string;
    ts?: string;
    recordingUrl?: string;
  }>;
  narrative?: ReportNarrativeView;
  cheapestVendorId?: string;
  warnings?: Array<{
    id: string;
    severity: "risk" | "caution";
    message: string;
    vendorId?: string;
    ts?: string;
    excerpt?: string;
  }>;
  disclaimer?: string;
  synthetic?: boolean;
}

export interface JobEventView {
  ts: string;
  type: string;
  jobId: string;
  message: string;
}

export type IntakeVariant = "clean" | "missing" | "warnings";
