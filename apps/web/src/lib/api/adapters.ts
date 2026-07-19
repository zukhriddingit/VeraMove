import type {
  CallRecord,
  JobRecord,
  JobSpecV1,
  QuoteV1,
  RecommendationV1,
  VendorDiscoveryResponse,
} from "@/api/client";
import type {
  CallView,
  EvidenceView,
  JobEventView,
  JobView,
  NegotiationView,
  RankedVendorView,
  ReportView,
  RequirementId,
  RequirementView,
  VendorView,
} from "./types";

function number(value: string | number | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function addressParts(summary?: string | null): { city: string; state: string } {
  if (!summary) return { city: "", state: "" };
  const parts = summary.split(",").map((part) => part.trim()).filter(Boolean);
  if (parts.length < 2) return { city: summary, state: "" };
  return { city: parts.slice(0, -1).join(", "), state: parts.at(-1) ?? "" };
}

function missingRequiredFields(spec: JobSpecV1): string[] {
  const missing: string[] = [];
  if (!spec.move_date) missing.push("move.date");
  if (spec.date_flexible === null || spec.date_flexible === undefined) {
    missing.push("move.flexibilityDays");
  }
  if (spec.bedroom_count === null || spec.bedroom_count === undefined) missing.push("homeType");
  if (!spec.insurance_preference) missing.push("services.insuranceTier");
  if (!spec.inventory?.length) missing.push("inventory");
  if (!spec.origin.address_summary || !spec.destination.address_summary) missing.push("move.route");
  if (!spec.origin.dwelling_type || !spec.destination.dwelling_type) missing.push("homeType");
  if (
    spec.origin.floors === null ||
    spec.origin.floors === undefined ||
    spec.origin.stairs === null ||
    spec.origin.stairs === undefined ||
    spec.origin.elevator_access === null ||
    spec.origin.elevator_access === undefined
  ) {
    missing.push("access.origin");
  }
  if (
    spec.destination.floors === null ||
    spec.destination.floors === undefined ||
    spec.destination.stairs === null ||
    spec.destination.stairs === undefined ||
    spec.destination.elevator_access === null ||
    spec.destination.elevator_access === undefined ||
    spec.destination.parking_distance_feet === null ||
    spec.destination.parking_distance_feet === undefined
  ) {
    missing.push("access.destination");
  }
  if (spec.origin.parking_distance_feet === null || spec.origin.parking_distance_feet === undefined) {
    missing.push("access.longCarryFt");
  }
  if (spec.services?.packing === null || spec.services?.packing === undefined) {
    missing.push("services.packing");
  }
  if (spec.services?.disassembly === null || spec.services?.disassembly === undefined) {
    missing.push("extras.disassembly");
  }
  if (spec.services?.storage === null || spec.services?.storage === undefined) {
    missing.push("extras.storage");
  }
  return [...new Set(missing)];
}

export function toJobView(record: JobRecord): JobView {
  const spec = record.job_spec;
  const origin = addressParts(spec.origin.address_summary);
  const destination = addressParts(spec.destination.address_summary);
  const source = spec.intake_source === "voice" || spec.intake_source === "document"
    ? spec.intake_source
    : "manual";
  return {
    id: spec.job_id ?? "",
    version: Number(spec.version),
    status: record.state,
    synthetic: spec.data_classification !== "real_redacted",
    homeType: spec.origin.dwelling_type ?? spec.destination.dwelling_type ?? "other",
    bedrooms: spec.bedroom_count ?? undefined,
    move: {
      originCity: origin.city,
      originState: origin.state,
      destinationCity: destination.city,
      destinationState: destination.state,
      date: spec.move_date ?? "",
      flexibilityDays: spec.date_flexible ? 1 : 0,
    },
    access: {
      originFloor: spec.origin.floors ?? 0,
      originElevator: spec.origin.elevator_access ?? false,
      destinationFloor: spec.destination.floors ?? 0,
      destinationElevator: spec.destination.elevator_access ?? false,
      longCarryFt: spec.origin.parking_distance_feet ?? 0,
    },
    inventory: (spec.inventory ?? []).map((item) => ({
      item: item.name,
      qty: item.quantity,
      notes: item.notes ?? undefined,
    })),
    services: {
      packing: spec.services?.packing ?? false,
      insuranceTier: spec.insurance_preference?.toLowerCase().includes("full")
        ? "full-value"
        : "standard",
    },
    extras: {
      disassembly: spec.services?.disassembly ?? false,
      storage: spec.services?.storage ?? false,
      oversizedOrFragile: spec.oversized_or_fragile_items ?? [],
    },
    missingFields: missingRequiredFields(spec),
    extractionSource: source,
    createdAt: record.created_at,
    confirmedAt: spec.confirmed_at ?? undefined,
  };
}

function secondsLabel(value: string): string {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function requirement(
  id: RequirementId,
  label: string,
  quote: QuoteV1 | null | undefined,
  terms: string[],
): RequirementView {
  const match = quote?.transcript_evidence?.find((item) => {
    const text = `${item.claim} ${item.excerpt}`.toLowerCase();
    return terms.some((term) => text.includes(term));
  });
  const evidence: EvidenceView | undefined = match
    ? { callId: match.call_id, ts: secondsLabel(match.start_seconds), excerpt: match.excerpt }
    : undefined;
  return { id, label, state: evidence ? "passed" : "pending", evidence };
}

function vendorKind(vendor: CallRecord["vendor"]): VendorView["kind"] {
  const summary = `${vendor.name} ${vendor.behavior_summary}`.toLowerCase();
  if (summary.includes("premium")) return "premium";
  if (summary.includes("budget") || summary.includes("low")) return "budget";
  return "transparent";
}

function negotiationView(quote?: QuoteV1 | null): NegotiationView | undefined {
  const before = number(quote?.original_total);
  const after = number(quote?.negotiated_total);
  if (before === undefined || after === undefined || after >= before) return undefined;
  return {
    beforeTotal: before,
    afterTotal: after,
    delta: before - after,
    leverageVendorId: "",
    addedInclusions: quote?.concessions ?? [],
  };
}

export function toCallView(call: CallRecord): CallView {
  const quote = call.outcome.quote;
  const fees = (quote?.fee_line_items ?? []).map((fee) => ({
    label: fee.description,
    amount: number(fee.amount) ?? 0,
    note: fee.category.replaceAll("_", " "),
    revealedAfterQuestioning: !fee.disclosed_upfront,
  }));
  const evidence = quote?.transcript_evidence ?? [];
  const redFlags = [
    ...(quote?.red_flags ?? []).map((message, index) => ({
      id: `${call.call_id}-red-flag-${index}`,
      severity: "risk" as const,
      message,
    })),
    ...(quote?.findings ?? [])
      .filter((finding) => finding.severity !== "info")
      .map((finding, index) => ({
        id: `${call.call_id}-finding-${index}`,
        severity: finding.severity === "critical" ? "risk" as const : "caution" as const,
        message: finding.description,
      })),
  ];
  const started = new Date(call.started_at).getTime();
  const completed = call.completed_at ? new Date(call.completed_at).getTime() : started;
  return {
    id: call.call_id,
    jobId: call.job_id,
    vendor: {
      id: call.vendor.vendor_id,
      name: call.vendor.name,
      kind: vendorKind(call.vendor),
    },
    status: call.status,
    outcome: call.outcome.type,
    headlineQuote: number(quote?.headline_total),
    verifiedTotal: number(quote?.negotiated_total ?? quote?.comparable_total),
    binding: quote?.binding_type === "binding",
    fees,
    hiddenFees: fees.filter((fee) => fee.revealedAfterQuestioning),
    redFlags,
    requirements: [
      requirement("ai_disclosure", "AI identity disclosed", quote, ["ai", "automated", "assistant"]),
      requirement("friction_handled", "Fees and constraints probed", quote, ["fee", "stairs", "carry", "deposit"]),
      requirement("verified_leverage", "Verified leverage used", quote, ["leverage", "competing", "match"]),
      requirement("structured_ending", "Commitment and next step captured", quote, ["binding", "availability", "commit"]),
    ],
    transcript: evidence.map((item) => ({
      ts: secondsLabel(item.start_seconds),
      speaker: "vendor" as const,
      text: item.excerpt,
    })),
    recording: call.recording_url
      ? { url: call.recording_url, durationSec: Math.max(0, Math.round((completed - started) / 1000)) }
      : undefined,
    negotiation: negotiationView(quote),
    startedAt: call.started_at,
    endedAt: call.completed_at ?? undefined,
  };
}

function quoteFor(record: JobRecord, quoteId: string): QuoteV1 | undefined {
  return record.quotes?.find((quote) => quote.quote_id === quoteId);
}

function rankingView(
  ranking: RecommendationV1["rankings"][number],
  recommendation: RecommendationV1,
  record: JobRecord,
): RankedVendorView {
  const quote = quoteFor(record, ranking.quote_id);
  const total = number(ranking.total);
  const label = ranking.vendor.vendor_id === recommendation.winning_vendor_id
    ? "Recommended"
    : ranking.vendor.vendor_id === recommendation.cheapest_vendor_id
      ? "Cheapest"
      : ranking.vendor.vendor_id === recommendation.best_value_vendor_id
        ? "Best value"
        : undefined;
  return {
    vendorId: ranking.vendor.vendor_id,
    vendorName: ranking.vendor.name,
    finalTotal: total,
    binding: quote?.binding_type === "binding",
    reasons: ranking.rationale,
    label,
    headlineTotal: number(quote?.headline_total),
    verifiedTotal: number(quote?.comparable_total),
    negotiatedTotal: number(quote?.negotiated_total),
    verificationState: quote?.verification_status,
    availability: quote?.availability,
    deposit: number(quote?.deposit),
    concessions: quote?.concessions ?? [],
    hiddenFeeCount: quote?.fee_line_items.filter((fee) => !fee.disclosed_upfront).length ?? 0,
    redFlagCount: ranking.red_flags?.length ?? 0,
    evidenceCount: ranking.evidence_ids.length,
    hasRecording: Boolean(quote?.recording_url),
    completeness: quote ? "complete" : "partial",
    warnings: ranking.red_flags ?? [],
    synthetic: ranking.vendor.data_classification !== "real_redacted",
  };
}

export function toReportView(recommendation: RecommendationV1, record: JobRecord): ReportView {
  const ranking = recommendation.rankings.map((item) =>
    rankingView(item, recommendation, record));
  const totals = ranking
    .map((item) => item.negotiatedTotal ?? item.verifiedTotal ?? item.finalTotal)
    .filter((value): value is number => value !== undefined)
    .sort((a, b) => a - b);
  const median = totals.length
    ? totals.length % 2
      ? totals[Math.floor(totals.length / 2)]
      : ((totals[totals.length / 2 - 1] ?? 0) + (totals[totals.length / 2] ?? 0)) / 2
    : undefined;
  const winner = ranking.find((item) => item.vendorId === recommendation.winning_vendor_id);
  const highest = totals.at(-1);
  const winningTotal = winner?.negotiatedTotal ?? winner?.verifiedTotal ?? winner?.finalTotal;
  const callById = new Map((record.calls ?? []).map((call) => [call.call_id, call]));
  return {
    jobId: recommendation.job_id,
    ranking,
    recommended: {
      vendorId: recommendation.winning_vendor_id,
      label: winner?.label ?? "Recommended",
      tradeoffs: [...(recommendation.assumptions ?? []), ...(recommendation.uncertainty ?? [])],
      savingsVsHighest: highest !== undefined && winningTotal !== undefined
        ? Math.max(0, highest - winningTotal)
        : 0,
    },
    medianVerifiedTotal: median,
    evidenceIndex: recommendation.transcript_evidence.map((item) => ({
      callId: item.call_id,
      vendorName: callById.get(item.call_id)?.vendor.name ?? "Vendor",
      note: item.claim,
      ts: secondsLabel(item.start_seconds),
      recordingUrl: item.recording_url,
    })),
    narrative: {
      whyThisVendor: recommendation.summary,
      remainingUncertainty: recommendation.uncertainty?.join(" "),
      whatToVerify: recommendation.assumptions?.join(" "),
    },
    cheapestVendorId: recommendation.cheapest_vendor_id ?? undefined,
    warnings: (recommendation.hidden_fee_findings ?? []).map((finding, index) => ({
      id: `finding-${index}`,
      severity: finding.severity === "critical" ? "risk" : "caution",
      message: finding.description,
      vendorId: finding.vendor_id ?? undefined,
    })),
    disclaimer: "Verify final terms with the selected mover before booking.",
    synthetic: record.job_spec.data_classification !== "real_redacted",
  };
}

export function toJobEventView(event: {
  occurred_at: string;
  event_type: string;
  job_id: string;
  metadata?: Record<string, string | number | boolean | null>;
}): JobEventView {
  const message = event.metadata?.message;
  return {
    ts: event.occurred_at,
    type: event.event_type,
    jobId: event.job_id,
    message: typeof message === "string" ? message : event.event_type.replaceAll("_", " "),
  };
}

export function toVendorViews(response: VendorDiscoveryResponse): VendorView[] {
  return response.vendors.map((vendor) => ({
    id: vendor.vendor_id,
    name: vendor.name,
    kind: vendorKind(vendor),
  }));
}
