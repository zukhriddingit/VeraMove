import type { ReportView } from "@/lib/api/types";
import { AlertTriangle, ShieldAlert } from "lucide-react";
import { TranscriptExcerpt } from "./TranscriptExcerpt";

/**
 * Renders only the warnings the backend supplies. Never derives risk from
 * a local threshold (no "30% below median" rule in the frontend).
 */
export function HiddenFeeWarnings({ report }: { report: ReportView }) {
  const warnings = report.warnings ?? [];
  if (warnings.length === 0) return null;

  const nameFor = (id?: string) =>
    id ? report.ranking.find((r) => r.vendorId === id)?.vendorName : undefined;

  return (
    <section
      aria-labelledby="hidden-fee-warnings-title"
      className="rounded-2xl border border-risk/30 bg-risk-soft p-5"
    >
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-risk-foreground">
        <ShieldAlert className="h-4 w-4" aria-hidden />
        Hidden-fee & risk findings
      </div>
      <h3 id="hidden-fee-warnings-title" className="sr-only">
        Hidden fee warnings
      </h3>
      <ul className="mt-3 space-y-3">
        {warnings.map((w) => (
          <li
            key={w.id}
            className="rounded-lg border border-border bg-surface p-3"
          >
            <div className="flex items-start gap-2 text-sm">
              <AlertTriangle
                className={
                  "mt-0.5 h-4 w-4 shrink-0 " +
                  (w.severity === "risk" ? "text-risk" : "text-caution-foreground")
                }
                aria-hidden
              />
              <div>
                <div className="font-medium">{w.message}</div>
                {nameFor(w.vendorId) && (
                  <div className="text-xs text-muted-foreground">
                    {nameFor(w.vendorId)}
                  </div>
                )}
              </div>
            </div>
            {(w.excerpt || w.ts) && (
              <TranscriptExcerpt
                className="mt-2"
                ts={w.ts}
                excerpt={w.excerpt}
                vendorName={nameFor(w.vendorId)}
              />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
