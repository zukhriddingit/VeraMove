// Demo adapter — mirrors the shape of the live endpoints module so components
// don't care which is wired.

import type { CallViewStatus, IntakeVariant, JobEventView, JobView, ReportView, VendorView, CallView } from "../types";
import {
  DEMO_JOB_ID,
  demoCalls,
  demoJobSpec,
  demoJobSpecMissing,
  demoJobSpecWarnings,
  demoReport,
} from "./fixtures";

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

// In-memory store so intake variants persist across the navigation to /confirm.
// Keyed by jobId. Resets on full reload — intentional for demo mode.
const jobStore = new Map<string, JobView>([[DEMO_JOB_ID, { ...demoJobSpec }]]);

function pickVariant(v?: IntakeVariant): JobView {
  if (v === "missing") return { ...demoJobSpecMissing };
  if (v === "warnings") return { ...demoJobSpecWarnings };
  return { ...demoJobSpec };
}

export async function getJob(jobId: string): Promise<JobView> {
  await delay(150);
  const j = jobStore.get(jobId);
  if (!j) throw new Error("Job not found");
  // Async negotiation completion: transition negotiating → completed after
  // the demo delay so consumers polling getJob see the same state machine
  // the live backend produces.
  const negStart = negotiationStartedAt.get(jobId);
  if (j.status === "negotiating" && negStart && Date.now() - negStart >= NEGOTIATION_MS) {
    const next: JobView = { ...j, status: "completed" };
    jobStore.set(jobId, next);
    return { ...next };
  }
  return { ...j };
}

export async function confirmJob(jobId: string): Promise<JobView> {
  await delay(200);
  const j = jobStore.get(jobId);
  if (!j) throw new Error("Job not found");
  const confirmed: JobView = {
    ...j,
    status: "confirmed",
    confirmedAt: new Date().toISOString(),
  };
  jobStore.set(jobId, confirmed);
  return { ...confirmed };
}

// Frontend-only local update used before confirmation. Live mode would PATCH
// the backend instead; this keeps the demo adapter self-contained.
export async function updateJob(jobId: string, patch: Partial<JobView>): Promise<JobView> {
  await delay(80);
  const j = jobStore.get(jobId);
  if (!j) throw new Error("Job not found");
  const next: JobView = { ...j, ...patch };
  jobStore.set(jobId, next);
  return { ...next };
}

// Track when the three calls were kicked off per job — drives simulated
// cascading progress (queued → dialing → in_progress → completed) and the
// eventual `calling → quotes_ready` job transition.
const callsStartedAt = new Map<string, number>();

function progressCalls(startedMs: number): CallView[] {
  const elapsed = Date.now() - startedMs;
  const phases: CallViewStatus[] = ["dialing", "queued", "queued"];
  if (elapsed >= 500) phases[0] = "completed";
  if (elapsed >= 500 && elapsed < 1000) phases[1] = "dialing";
  if (elapsed >= 1000) phases[1] = "completed";
  if (elapsed >= 1000 && elapsed < 1500) phases[2] = "in_progress";
  if (elapsed >= 1500) phases[2] = "completed";
  return demoCalls.map((c, i) => {
    const status = phases[i];
    if (status === "completed") return c;
    return {
      ...c,
      status,
      outcome: undefined,
      verifiedTotal: undefined,
      fees: [],
      hiddenFees: [],
      redFlags: [],
      requirements: c.requirements.map((r) => ({ ...r, state: "pending" as const, evidence: undefined })),
      transcript: [],
      recording: undefined,
      negotiation: undefined,
      endedAt: undefined,
    };
  });
}

export async function getCalls(jobId: string): Promise<CallView[]> {
  await delay(120);
  if (jobId !== DEMO_JOB_ID) return [];
  const j = jobStore.get(jobId);
  // Before user hits "Start three vendor calls" there are no calls to show.
  if (!j || j.status === "draft" || j.status === "intake_complete" || j.status === "confirmed") {
    return [];
  }
  const startedMs = callsStartedAt.get(jobId);
  if (j.status === "calling" && startedMs) {
    // Advance job to quotes_ready once cascade is done.
    if (Date.now() - startedMs >= 1500) {
      jobStore.set(jobId, { ...j, status: "quotes_ready" });
      return callsWithoutNegotiation();
    }
    return progressCalls(startedMs);
  }
  // NegotiationView result on call-c is only materialized once the workflow
  // finishes — before that, expose the pre-negotiation quote only.
  if (j.status === "completed") return demoCalls;
  return callsWithoutNegotiation();
}

function callsWithoutNegotiation(): CallView[] {
  return demoCalls.map((c) => (c.negotiation ? { ...c, negotiation: undefined } : c));
}

export async function startCalls(jobId: string): Promise<CallView[]> {
  await delay(200);
  const j = jobStore.get(jobId);
  if (!j) throw new Error("Job not found");
  if (j.status !== "confirmed" && j.status !== "calling") {
    throw new Error(`Cannot start calls from state "${j.status}"`);
  }
  jobStore.set(jobId, { ...j, status: "calling" });
  callsStartedAt.set(jobId, Date.now());
  return progressCalls(Date.now());
}

// Track when negotiation kicked off per job so getJob can transition
// `negotiating` → `completed` asynchronously (mirrors how the live backend
// may complete either immediately or after a short async delay).
const negotiationStartedAt = new Map<string, number>();
const NEGOTIATION_MS = 1800;

export async function negotiateJob(jobId: string) {
  await delay(220);
  const j = jobStore.get(jobId);
  if (!j) throw new Error("Job not found");
  if (j.status !== "quotes_ready" && j.status !== "negotiating") {
    throw new Error(`Cannot negotiate from state "${j.status}"`);
  }
  jobStore.set(jobId, { ...j, status: "negotiating" });
  negotiationStartedAt.set(jobId, Date.now());
  const target = demoCalls.find((c) => c.negotiation);
  const n = target?.negotiation;
  return n
    ? { ...n }
    : { beforeTotal: 0, afterTotal: 0, delta: 0, leverageVendorId: "", addedInclusions: [] };
}

export async function getReport(jobId: string): Promise<ReportView> {
  await delay(200);
  if (jobId !== DEMO_JOB_ID) throw new Error("Report not ready");
  return demoReport;
}

export async function getEvents(jobId: string): Promise<JobEventView[]> {
  await delay(100);
  if (jobId !== DEMO_JOB_ID) return [];
  return [
    { ts: "14:18:00", type: "call.started", jobId, message: "Dialing ClearPath Movers" },
    { ts: "14:25:08", type: "call.completed", jobId, message: "ClearPath — itemized binding quote $1,825" },
    { ts: "14:26:00", type: "call.started", jobId, message: "Dialing BudgetHaul Express" },
    { ts: "14:33:01", type: "call.completed", jobId, message: "BudgetHaul — hidden fees surfaced, non-binding $1,850" },
    { ts: "14:34:00", type: "call.started", jobId, message: "Dialing PremierMove" },
    { ts: "14:39:11", type: "negotiation.started", jobId, message: "Using ClearPath's $1,825 as verified leverage" },
    { ts: "14:42:32", type: "call.completed", jobId, message: "PremierMove — $2,200 → $1,900 binding, packing materials added" },
    { ts: "14:42:40", type: "report.ready", jobId, message: "Ranked recommendation ready" },
  ];
}

/**
 * Simulated Tavily-style discovery candidates. Distinct set from the three
 * role-play vendors that actually get called — this is "where a production
 * call list would come from," not the current demonstration.
 */
export async function getVendorsDiscovery(): Promise<VendorView[]> {
  await delay(120);
  return [
    { id: "disc-1", name: "Two Men and a Truck (Charlotte)", kind: "transparent" },
    { id: "disc-2", name: "Miracle Movers of Charlotte", kind: "transparent" },
    { id: "disc-3", name: "College Hunks Hauling Junk & Moving", kind: "budget" },
    { id: "disc-4", name: "All My Sons Moving & Storage", kind: "budget" },
    { id: "disc-5", name: "Bellhop Moving", kind: "premium" },
  ];
}

export async function createJobFromDocument(
  _file?: File,
  variant?: IntakeVariant,
): Promise<{ jobId: string }> {
  await delay(400);
  const spec = pickVariant(variant);
  spec.extractionSource = "document";
  jobStore.set(DEMO_JOB_ID, spec);
  return { jobId: DEMO_JOB_ID };
}

export async function createJobFromVoice(
  variant?: IntakeVariant,
): Promise<{ jobId: string }> {
  await delay(400);
  const spec = pickVariant(variant);
  spec.extractionSource = "voice";
  jobStore.set(DEMO_JOB_ID, spec);
  return { jobId: DEMO_JOB_ID };
}
