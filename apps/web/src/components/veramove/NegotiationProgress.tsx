import type { JobEventView } from "@/lib/api";
import { StatusPill } from "./StatusPill";
import { Loader2, PhoneOutgoing } from "lucide-react";

/**
 * Progress panel shown while job.status === "negotiating".
 *
 * The backend currently exposes a single "negotiating" status without
 * granular sub-events. We render a generic progress indicator plus any
 * negotiation-tagged events the backend has emitted, rather than
 * fabricating sub-phases.
 */
export function NegotiationProgress({
  events,
  demo,
}: {
  events: JobEventView[];
  demo: boolean;
}) {
  const relevant = events.filter((e) => e.type.startsWith("negotiation"));

  return (
    <section className="rounded-2xl border border-border bg-surface p-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <PhoneOutgoing className="h-3.5 w-3.5" /> Negotiation in progress
        </div>
        {demo ? <StatusPill tone="info">Role-play</StatusPill> : null}
      </header>

      <div
        className="mt-3 flex items-center gap-3 rounded-xl border border-border bg-background p-4"
        role="status"
        aria-live="polite"
      >
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        <div>
          <div className="text-sm font-medium">Working on the target vendor</div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Applying verified competing leverage. Waiting on canonical result
            from the backend.
          </p>
        </div>
      </div>

      {relevant.length > 0 && (
        <ol className="mt-4 space-y-2 text-sm">
          {relevant.map((e, i) => (
            <li
              key={i}
              className="grid grid-cols-[64px_1fr] gap-3 rounded-md border border-border bg-background px-3 py-2"
            >
              <span className="tabular-nums text-xs text-muted-foreground">
                {e.ts}
              </span>
              <span>{e.message}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
