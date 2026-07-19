// Shared "what can the user do right now?" helper. Derived entirely from
// backend job state so every page component asks the same source of truth
// instead of scattering `job.status === "…"` checks.

import type { JobView, JobViewState } from "./types";

export interface JobActions {
  /** Can the user still edit intake fields? Blocked once the spec is locked. */
  canEditIntake: boolean;
  /** Confirm-and-lock the current draft. */
  canConfirm: boolean;
  /** Kick off the three vendor calls. */
  canStartCalls: boolean;
  /** Move to the negotiation stage. */
  canNegotiate: boolean;
  /** Report is ready to view. */
  canViewReport: boolean;
  /** Terminal-failure state — surface an error banner. */
  isFailed: boolean;
}

const DRAFT_STATES = new Set<JobViewState>(["draft", "intake_complete"]);

export function jobActions(job: Pick<JobView, "status" | "missingFields"> | undefined | null): JobActions {
  if (!job) {
    return {
      canEditIntake: false,
      canConfirm: false,
      canStartCalls: false,
      canNegotiate: false,
      canViewReport: false,
      isFailed: false,
    };
  }
  const noBlockers = (job.missingFields?.length ?? 0) === 0;
  const s = job.status;
  return {
    canEditIntake: DRAFT_STATES.has(s),
    canConfirm: s === "intake_complete" && noBlockers,
    canStartCalls: s === "confirmed",
    canNegotiate: s === "quotes_ready",
    canViewReport: s === "completed",
    isFailed: s === "failed",
  };
}

/** Hook wrapper — components normally just do `jobActions(job)`, but this
 *  gives a hook-shaped API for parity with react-query call sites. */
export function useJobActions(job: JobView | undefined | null): JobActions {
  return jobActions(job);
}
