import type { IntakeSessionResponse } from "@/api/client";

export type BrowserVoicePhase =
  | "ready"
  | "requesting_microphone"
  | "connecting"
  | "connected"
  | "finalizing"
  | "incomplete"
  | "completed"
  | "unavailable"
  | "failed";

export const POLL_ATTEMPTS_BEFORE_RECOVERY = 8;

export type PollDecision =
  { kind: "apply" } | { kind: "poll" } | { kind: "recover" } | { kind: "unavailable" };

const TERMINAL_STATUSES = new Set<IntakeSessionResponse["status"]>([
  "incomplete",
  "completed",
  "failed",
]);

export function nextVoicePhase(
  session: Pick<IntakeSessionResponse, "status" | "job_spec" | "partial_job_spec">,
): BrowserVoicePhase | null {
  if (session.status === "completed") return session.job_spec ? "completed" : "failed";
  if (session.status === "incomplete") {
    return session.partial_job_spec ? "incomplete" : "failed";
  }
  if (session.status === "failed") return "failed";
  return null;
}

export function pollDecision(
  completedAttempts: number,
  status: IntakeSessionResponse["status"],
): PollDecision {
  if (TERMINAL_STATUSES.has(status)) return { kind: "apply" };
  if (completedAttempts < POLL_ATTEMPTS_BEFORE_RECOVERY) return { kind: "poll" };
  if (completedAttempts === POLL_ATTEMPTS_BEFORE_RECOVERY) return { kind: "recover" };
  return { kind: "unavailable" };
}
