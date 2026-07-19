import { Link, useLocation, useParams } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useJob } from "@/lib/api/hooks";
import type { JobViewState } from "@/lib/api/types";

type Stage = "intake" | "confirm" | "calls" | "negotiate" | "report";

const STAGES: { id: Stage; label: string; match: (path: string) => boolean }[] = [
  { id: "intake", label: "Intake", match: (p) => p === "/" || p.startsWith("/intake") },
  { id: "confirm", label: "Confirm", match: (p) => p.startsWith("/confirm") },
  { id: "calls", label: "Calls", match: (p) => p.startsWith("/calls") },
  { id: "negotiate", label: "Negotiate", match: (p) => p.startsWith("/negotiate") },
  { id: "report", label: "Report", match: (p) => p.startsWith("/report") },
];

// Canonical state machine → furthest completed stage index.
// draft/intake_complete → intake done; confirmed → confirm done;
// calling → calls active; quotes_ready → calls done, negotiate active;
// negotiating → negotiate active; completed → report active.
// "failed" intentionally omitted — we preserve the last meaningful stage
// derived from URL / prior data and surface the failure separately.
const STATUS_TO_ACTIVE: Partial<Record<JobViewState, number>> = {
  draft: 0,
  intake_complete: 1,
  confirmed: 2,
  calling: 2,
  quotes_ready: 3,
  negotiating: 3,
  completed: 4,
};

export function JourneyStepper() {
  const { pathname } = useLocation();
  const params = useParams({ strict: false }) as { jobId?: string };
  const jobQ = useJob(params.jobId ?? "");

  const pathActive = STAGES.findIndex((s) => s.match(pathname));
  const status = jobQ.data?.status;
  const isFailed = status === "failed";
  // Prefer backend job status when we have it — the URL alone can lie
  // (e.g. bookmarking /confirm after backend already moved to calling).
  // For "failed", keep whatever the last meaningful stage was (URL-derived).
  const statusActive =
    status && STATUS_TO_ACTIVE[status] !== undefined ? STATUS_TO_ACTIVE[status]! : -1;
  const activeIdx = statusActive >= 0 ? Math.max(pathActive, statusActive) : pathActive;

  return (
    <nav aria-label="Journey progress" className="w-full">
      <ol className="flex items-center gap-2 overflow-x-auto py-1 md:gap-3">
        {STAGES.map((s, i) => {
          const isCurrentStage = i === activeIdx;
          const state: "done" | "active" | "failed" | "todo" =
            isFailed && isCurrentStage
              ? "failed"
              : i < activeIdx
                ? "done"
                : isCurrentStage
                  ? "active"
                  : "todo";
          return (
            <li key={s.id} className="flex items-center gap-2 md:gap-3">
              <div
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap",
                  state === "active" &&
                    "border-primary bg-primary text-primary-foreground",
                  state === "done" &&
                    "border-verified bg-verified-soft text-foreground",
                  state === "failed" &&
                    "border-risk bg-risk-soft text-risk-foreground",
                  state === "todo" &&
                    "border-border bg-surface text-muted-foreground",
                )}
                aria-current={state === "active" || state === "failed" ? "step" : undefined}
              >
                <span
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full text-[10px]",
                    state === "active" && "bg-primary-foreground/20",
                    state === "done" && "bg-verified text-verified-foreground",
                    state === "failed" && "bg-risk text-risk-foreground",
                    state === "todo" && "bg-muted",
                  )}
                >
                  {state === "done" ? <Check className="h-3 w-3" /> : state === "failed" ? "!" : i + 1}
                </span>
                <span>{s.label}{state === "failed" ? " · failed" : ""}</span>
              </div>
              {i < STAGES.length - 1 && (
                <div
                  className={cn(
                    "hidden h-px w-8 sm:block",
                    i < activeIdx ? "bg-verified" : "bg-border",
                  )}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function JourneyLinks({ jobId }: { jobId?: string }) {
  if (!jobId) return null;
  return (
    <div className="flex gap-2 text-xs text-muted-foreground">
      <Link to="/confirm/$jobId" params={{ jobId }} className="hover:text-foreground">Confirm</Link>
      <Link to="/calls/$jobId" params={{ jobId }} className="hover:text-foreground">Calls</Link>
      <Link to="/negotiate/$jobId" params={{ jobId }} className="hover:text-foreground">Negotiate</Link>
      <Link to="/report/$jobId" params={{ jobId }} className="hover:text-foreground">Report</Link>
    </div>
  );
}
