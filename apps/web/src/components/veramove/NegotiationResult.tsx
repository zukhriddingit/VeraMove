import type { NegotiationView, CallView } from "@/lib/api";
import { NegotiationDelta } from "./NegotiationDelta";
import { TranscriptExcerpt } from "./Transcript";
import { StatusPill } from "./StatusPill";
import { usd } from "@/lib/format";
import { CheckCircle2, ShieldCheck, ShieldAlert } from "lucide-react";

/**
 * Full negotiation result panel. Renders backend-supplied fields only —
 * we do not independently infer concessions, choose a target, or compute
 * savings that the backend didn't return.
 *
 * If a call carrying transcript evidence is not available, the result is
 * labeled Provisional and no Verified badge is shown.
 */
export function NegotiationResult({
  negotiation,
  targetCall,
  leverageCall,
  demo,
}: {
  negotiation: NegotiationView;
  targetCall?: CallView;
  leverageCall?: CallView;
  demo: boolean;
}) {
  const hasEvidence = !!targetCall && (targetCall.transcript.length > 0 || !!targetCall.recording);
  const verified = hasEvidence && !!targetCall && targetCall.status === "completed";
  const priceImproved = negotiation.delta < 0;
  const termsImproved = negotiation.addedInclusions.length > 0;

  return (
    <section className="rounded-2xl border border-border bg-surface p-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Negotiation result
          </div>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">
            {targetCall ? targetCall.vendor.name : "Target vendor"}
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {verified ? (
            <StatusPill tone="verified" icon={<ShieldCheck className="h-3.5 w-3.5" />}>
              Verified
            </StatusPill>
          ) : (
            <StatusPill tone="caution" icon={<ShieldAlert className="h-3.5 w-3.5" />}>
              Provisional — awaiting evidence
            </StatusPill>
          )}
          {demo ? <StatusPill tone="info">Role-play</StatusPill> : null}
        </div>
      </header>

      {priceImproved || !termsImproved ? (
        <div className="mt-4">
          <NegotiationDelta
            negotiation={negotiation}
            leverageVendorName={leverageCall?.vendor.name}
          />
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-verified/30 bg-verified-soft p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Terms improved
          </div>
          <div className="mt-1 text-sm">
            Price held at{" "}
            <span className="font-semibold tabular-nums">
              {usd(negotiation.afterTotal)}
            </span>
            . New inclusions:{" "}
            <span className="font-medium">
              {negotiation.addedInclusions.join(", ")}
            </span>
            .
          </div>
        </div>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <ResultCell label="Original price" value={usd(negotiation.beforeTotal)} />
        <ResultCell label="Negotiated price" value={usd(negotiation.afterTotal)} />
        <ResultCell
          label="Price savings"
          value={priceImproved ? `− ${usd(Math.abs(negotiation.delta))}` : "No change"}
          tone={priceImproved ? "verified" : "neutral"}
        />
        <ResultCell
          label="Added inclusions"
          value={
            termsImproved ? negotiation.addedInclusions.join(", ") : "None reported"
          }
        />
      </div>

      {leverageCall && (
        <div className="mt-4 rounded-xl border border-border bg-background p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Verified competing quote used
          </div>
          <div className="mt-1 text-sm">
            {leverageCall.vendor.name} —{" "}
            <span className="tabular-nums font-medium">
              {usd(leverageCall.verifiedTotal)}
            </span>
            {leverageCall.binding ? " · binding" : " · non-binding"}
          </div>
        </div>
      )}

      {targetCall && targetCall.transcript.length > 0 && (
        <div className="mt-4">
          <TranscriptExcerpt lines={targetCall.transcript} />
        </div>
      )}

      {targetCall?.endedAt && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
          <CheckCircle2 className="h-3.5 w-3.5 text-verified" />
          Negotiation completed at {new Date(targetCall.endedAt).toLocaleString()}
        </p>
      )}
    </section>
  );
}

function ResultCell({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "verified" | "neutral";
}) {
  return (
    <div className="rounded-xl border border-border bg-background p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={
          "mt-1 text-sm font-semibold tabular-nums " +
          (tone === "verified" ? "text-verified" : "text-foreground")
        }
      >
        {value}
      </div>
    </div>
  );
}
