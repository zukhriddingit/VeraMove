import type { NegotiationView } from "@/lib/api";
import { usd } from "@/lib/format";
import { ArrowRight, TrendingDown } from "lucide-react";

export function NegotiationDelta({
  negotiation,
  leverageVendorName,
}: {
  negotiation: NegotiationView;
  leverageVendorName?: string;
}) {
  const improved = negotiation.delta < 0;
  return (
    <div className="rounded-xl border border-verified/30 bg-verified-soft p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <TrendingDown className="h-3.5 w-3.5 text-verified" />
        Negotiated outcome
      </div>
      <div className="mt-2 flex flex-wrap items-baseline gap-2 text-sm">
        <span className="text-muted-foreground line-through tabular-nums">
          {usd(negotiation.beforeTotal)}
        </span>
        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-lg font-semibold tabular-nums">
          {usd(negotiation.afterTotal)}
        </span>
        {improved && (
          <span className="rounded-full bg-verified px-2 py-0.5 text-xs font-medium text-verified-foreground">
            {usd(Math.abs(negotiation.delta))} improvement
          </span>
        )}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Leverage: verified quote from {leverageVendorName ?? "competing vendor"}
        {negotiation.addedInclusions.length > 0 && (
          <>
            {" · "}Added inclusions: {negotiation.addedInclusions.join(", ")}
          </>
        )}
      </p>
    </div>
  );
}
