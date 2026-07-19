import type { CallView } from "@/lib/api";
import { usd } from "@/lib/format";
import { CallOutcomeBadge, CallStatusBadge } from "./CallBadges";
import { FeeBreakdown } from "./FeeBreakdown";
import { HiddenFeeAlert, RedFlagAlert } from "./Alerts";
import { ConversationChecklist } from "./ConversationChecklist";
import { TranscriptExcerpt, RecordingPlayer } from "./Transcript";
import { NegotiationDelta } from "./NegotiationDelta";
import { StatusPill } from "./StatusPill";
import { CheckCircle2, Sparkles, Info } from "lucide-react";

function vendorRoleLabel(kind: CallView["vendor"]["kind"]) {
  if (kind === "transparent") return "Transparent operator";
  if (kind === "budget") return "Low-headline operator";
  return "Premium operator";
}

export function VendorCallCard({
  call,
  leverageVendorName,
  synthetic = false,
  liveMaterializationPending = false,
}: {
  call: CallView;
  leverageVendorName?: string;
  /** Demo/role-play data. Adds explicit disclosure. */
  synthetic?: boolean;
  /** Live: call ended but canonical quote isn't materialized yet. */
  liveMaterializationPending?: boolean;
}) {
  const isDone = call.status === "completed";
  const outcome = call.outcome;
  const showQuote = isDone && outcome === "itemized_quote";
  const showCallback = isDone && outcome === "callback_commitment";
  const showDecline = isDone && outcome === "documented_decline";
  const showFailed = call.status === "failed" || outcome === "failed";
  const showPending = !isDone && !showFailed;

  return (
    <article
      className="flex h-full flex-col gap-4 rounded-2xl border border-border bg-surface p-5 shadow-sm"
      aria-label={`Vendor call: ${call.vendor.name}`}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <h3 className="truncate text-base font-semibold">{call.vendor.name}</h3>
            {synthetic && (
              <StatusPill tone="info" icon={<Sparkles className="h-3 w-3" />}>
                Role-play
              </StatusPill>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {vendorRoleLabel(call.vendor.kind)} · quote mode
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <CallStatusBadge status={call.status} />
          {(showQuote || showCallback || showDecline || showFailed) && (
            <CallOutcomeBadge outcome={outcome} />
          )}
        </div>
      </header>

      {synthetic && (
        <p className="rounded-md bg-surface-muted px-2.5 py-1.5 text-[11px] text-muted-foreground">
          Synthetic data · this vendor is a demonstration counterparty, not a
          real company.
        </p>
      )}

      {showPending && (
        <div className="rounded-xl border border-border bg-surface-muted p-4 text-sm text-muted-foreground">
          Call in progress. Fees, evidence, and verification will appear once
          the call ends.
        </div>
      )}

      {liveMaterializationPending && (
        <div className="rounded-xl border border-caution/40 bg-caution-soft p-4 text-sm text-caution-foreground">
          <div className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4" />
            <div>
              <div className="font-medium">
                Call completed. Structured quote materialization is pending.
              </div>
              <div className="mt-1 text-xs opacity-90">
                The transcript is being turned into an itemized quote — no
                verified totals are shown until the backend materializes them.
              </div>
            </div>
          </div>
        </div>
      )}

      {showQuote && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-border bg-surface-muted p-3">
            <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Headline
            </div>
            <div className="mt-0.5 text-lg font-semibold tabular-nums">
              {call.headlineQuote !== undefined
                ? `${usd(call.headlineQuote)} provisional`
                : "Not provided"}
            </div>
          </div>
          <div className="rounded-lg border border-border bg-surface-muted p-3">
            <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Verified total
            </div>
            <div className="mt-0.5 flex flex-wrap items-baseline gap-2 text-lg font-semibold tabular-nums">
              {call.verifiedTotal !== undefined ? (
                <>
                  {usd(call.verifiedTotal)}
                  {call.binding ? (
                    <StatusPill tone="verified" icon={<CheckCircle2 className="h-3 w-3" />}>
                      Binding
                    </StatusPill>
                  ) : (
                    <StatusPill tone="caution">Non-binding</StatusPill>
                  )}
                </>
              ) : (
                <span className="text-sm font-normal text-muted-foreground">
                  Awaiting verification
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {showCallback && (
        <div className="rounded-xl border border-caution/40 bg-caution-soft p-4 text-sm text-caution-foreground">
          Vendor committed to a callback. No quote total has been captured
          yet — this is not a complete quote.
        </div>
      )}

      {showDecline && (
        <div className="rounded-xl border border-border bg-surface-muted p-4 text-sm text-muted-foreground">
          Vendor documented a decline for this move. No quote total applies.
        </div>
      )}

      {showFailed && (
        <div className="rounded-xl border border-risk/30 bg-risk-soft p-4 text-sm">
          Call failed. Retry availability depends on the backend workflow.
        </div>
      )}

      {showQuote && (
        <>
          <RedFlagAlert flags={call.redFlags} />
          <HiddenFeeAlert fees={call.hiddenFees} />
          {call.negotiation && (
            <NegotiationDelta
              negotiation={call.negotiation}
              leverageVendorName={leverageVendorName}
            />
          )}
          <FeeBreakdown
            fees={call.fees}
            hiddenFees={call.hiddenFees}
            total={call.verifiedTotal}
          />
        </>
      )}

      {(isDone || showFailed) && (
        <ConversationChecklist requirements={call.requirements} />
      )}
      {isDone && call.transcript.length > 0 && (
        <TranscriptExcerpt lines={call.transcript} />
      )}
      {isDone && <RecordingPlayer recording={call.recording} />}
    </article>
  );
}
