import type { ReportView, CallView } from "@/lib/api/types";
import { usd } from "@/lib/format";
import { ArrowRight, TrendingDown } from "lucide-react";
import { TranscriptExcerpt } from "./TranscriptExcerpt";

/**
 * "Before → After" negotiation summary. Uses only backend-reported totals
 * and concessions; never recomputes savings.
 */
export function NegotiationSummary({
  report,
  calls,
}: {
  report: ReportView;
  calls: CallView[];
}) {
  const target = report.ranking.find(
    (r) => r.vendorId === report.recommended.vendorId,
  );
  const call = target ? calls.find((c) => c.vendor.id === target.vendorId) : undefined;
  const neg = call?.negotiation;

  if (!target) return null;
  if (
    target.headlineTotal === undefined &&
    target.negotiatedTotal === undefined &&
    !neg
  ) {
    return null;
  }

  const before = target.headlineTotal ?? neg?.beforeTotal;
  const after = target.negotiatedTotal ?? neg?.afterTotal;
  const savings =
    before !== undefined && after !== undefined ? before - after : neg?.delta;

  const leverageVendorName = neg
    ? calls.find((c) => c.vendor.id === neg.leverageVendorId)?.vendor.name
    : undefined;

  const leverageLine = call?.transcript.find((l) => l.tag === "leverage");

  return (
    <section
      aria-labelledby="negotiation-summary-title"
      className="rounded-2xl border border-border bg-surface p-5"
    >
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <TrendingDown className="h-3.5 w-3.5" aria-hidden />
        Negotiation summary
      </div>
      <h3 id="negotiation-summary-title" className="sr-only">
        Negotiation before and after
      </h3>

      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto_1fr_auto_1fr]">
        <Cell
          label="Original"
          value={before !== undefined ? usd(before) : "Not provided"}
          sub={target.vendorName}
        />
        <Arrow />
        <Cell
          label="Negotiated"
          value={after !== undefined ? usd(after) : "Not provided"}
          sub={target.binding ? "Binding" : "Non-binding"}
          highlight
        />
        <Arrow />
        <Cell
          label="Savings"
          value={
            savings !== undefined && savings > 0
              ? `- ${usd(savings)}`
              : "None reported"
          }
          sub="Backend-verified"
        />
      </div>

      {(target.concessions?.length ?? 0) > 0 && (
        <ul className="mt-3 grid gap-1.5 text-sm sm:grid-cols-2">
          {target.concessions!.map((c, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-verified" />
              {c}
            </li>
          ))}
        </ul>
      )}

      {(leverageVendorName || leverageLine) && (
        <div className="mt-4">
          <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Verified leverage source
            {leverageVendorName ? ` · ${leverageVendorName}` : ""}
          </div>
          <TranscriptExcerpt
            className="mt-1.5"
            ts={leverageLine?.ts}
            excerpt={leverageLine?.text}
            vendorName={leverageVendorName}
          />
        </div>
      )}

      {report.narrative?.whatChanged && (
        <p className="mt-4 rounded-md border border-border bg-surface-muted p-3 text-sm text-foreground/90">
          {report.narrative.whatChanged}
        </p>
      )}
    </section>
  );
}

function Cell({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={
        "rounded-lg border p-3 " +
        (highlight ? "border-verified/40 bg-verified-soft" : "border-border bg-surface-muted")
      }
    >
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function Arrow() {
  return (
    <div className="hidden items-center justify-center sm:flex">
      <ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden />
    </div>
  );
}
