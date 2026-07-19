import type { JobView, CallView } from "@/lib/api";
import { StatusPill } from "./StatusPill";
import { TranscriptExcerpt } from "./Transcript";
import { usd } from "@/lib/format";
import { CheckCircle2, Lock, ShieldCheck, Target } from "lucide-react";

/**
 * Preflight panel for /negotiate. Shows only backend-supplied facts —
 * never invents a competing quote or a dollar delta.
 *
 * Target vendor and competing-leverage selection are backend decisions.
 * If either is not exposed before POST /negotiate, we show a neutral
 * placeholder ("The backend will select an eligible verified competing
 * quote.") rather than picking one in the frontend.
 */
export function NegotiationPreflight({
  job,
  calls,
  demo,
}: {
  job: JobView;
  calls: CallView[];
  demo: boolean;
}) {
  // A call is only a valid *pre-declared* target if the backend has already
  // annotated it (e.g. via a `negotiation` field carrying leverageVendorId).
  // The current backend does not yet expose the pre-selection, so we treat
  // both as unknown and rely on a generic message.
  const preSelectedTarget = calls.find((c) => (c as unknown as { targetForNegotiation?: boolean }).targetForNegotiation);
  const preSelectedLeverageId = preSelectedTarget
    ? (preSelectedTarget as unknown as { plannedLeverageVendorId?: string }).plannedLeverageVendorId
    : undefined;
  const leverageCall = preSelectedLeverageId
    ? calls.find((c) => c.vendor.id === preSelectedLeverageId)
    : undefined;

  return (
    <section className="rounded-2xl border border-border bg-surface p-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Target className="h-3.5 w-3.5" /> Negotiation preflight
          </div>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">
            Ready to negotiate on one vendor
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone="info" icon={<Lock className="h-3.5 w-3.5" />}>
            JobSpec v{job.version} locked
          </StatusPill>
          {leverageCall ? (
            <StatusPill tone="verified" icon={<ShieldCheck className="h-3.5 w-3.5" />}>
              Verified leverage
            </StatusPill>
          ) : null}
          {demo ? <StatusPill tone="info">Role-play</StatusPill> : null}
        </div>
      </header>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-border bg-background p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Target vendor
          </div>
          {preSelectedTarget ? (
            <>
              <div className="mt-1 text-sm font-semibold">
                {preSelectedTarget.vendor.name}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                Original quote:{" "}
                <span className="tabular-nums text-foreground">
                  {usd(preSelectedTarget.verifiedTotal ?? preSelectedTarget.headlineQuote)}
                </span>
                {preSelectedTarget.binding ? " · binding" : " · non-binding"}
              </div>
            </>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              The backend will select the vendor to negotiate with based on the
              three completed quotes.
            </p>
          )}
        </div>

        <div className="rounded-xl border border-border bg-background p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Verified competing leverage
          </div>
          {leverageCall ? (
            <>
              <div className="mt-1 text-sm font-semibold">
                {leverageCall.vendor.name}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                Verified total:{" "}
                <span className="tabular-nums text-foreground">
                  {usd(leverageCall.verifiedTotal)}
                </span>
                {leverageCall.binding ? " · binding" : " · non-binding"}
              </div>
              {leverageCall.transcript.length > 0 && (
                <div className="mt-3">
                  <TranscriptExcerpt lines={leverageCall.transcript.slice(0, 2)} />
                </div>
              )}
            </>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              The backend will select an eligible verified competing quote.
            </p>
          )}
        </div>
      </div>

      <ul className="mt-4 space-y-1.5 text-sm text-muted-foreground">
        <li className="flex items-start gap-2">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-verified" />
          Available lever: cite a verified competing quote and request a match
          or better on binding total and inclusions.
        </li>
        <li className="flex items-start gap-2">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          Inventory and job facts are locked at version {job.version} and
          cannot be changed to secure a lower price.
        </li>
      </ul>

      <p className="mt-4 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
        VeraMove may use a verified competing quote. It never invents a bid,
        changes the inventory, or misrepresents the move.
      </p>
    </section>
  );
}
