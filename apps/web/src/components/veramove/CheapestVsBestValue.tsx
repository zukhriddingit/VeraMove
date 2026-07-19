import type { ReportView } from "@/lib/api/types";
import { usd } from "@/lib/format";
import { Scale } from "lucide-react";

/**
 * Renders the backend's "cheapest vs best value" distinction using only
 * fields it supplied. Never derives labels from local price comparison.
 */
export function CheapestVsBestValue({ report }: { report: ReportView }) {
  const rec = report.ranking.find((r) => r.vendorId === report.recommended.vendorId);
  const cheapest =
    (report.cheapestVendorId
      ? report.ranking.find((r) => r.vendorId === report.cheapestVendorId)
      : report.ranking.find((r) => r.label?.toLowerCase() === "cheapest")) ?? null;

  if (!rec || !cheapest || cheapest.vendorId === rec.vendorId) {
    // Backend did not distinguish the two — do nothing rather than inventing it.
    return null;
  }

  return (
    <section
      className="rounded-2xl border border-border bg-surface p-5"
      aria-labelledby="cheapest-vs-best-title"
    >
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Scale className="h-3.5 w-3.5" aria-hidden />
        Cheapest vs best value
      </div>
      <h3 id="cheapest-vs-best-title" className="sr-only">
        Cheapest vs best value comparison
      </h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Card
          heading="Cheapest"
          vendorName={cheapest.vendorName}
          total={cheapest.negotiatedTotal ?? cheapest.verifiedTotal ?? cheapest.finalTotal}
          detail={
            cheapest.binding
              ? "Binding · lowest headline price"
              : "Non-binding — final price may change"
          }
        />
        <Card
          heading={rec.label ?? "Best value"}
          vendorName={rec.vendorName}
          total={rec.negotiatedTotal ?? rec.verifiedTotal ?? rec.finalTotal}
          detail={
            rec.binding
              ? "Binding · recommended by backend"
              : "Non-binding · recommended by backend"
          }
          highlight
        />
      </div>
      {report.narrative?.whyNotCheapest && (
        <p className="mt-4 rounded-md border border-border bg-surface-muted p-3 text-sm text-foreground/90">
          <span className="font-medium">Why not simply pick the cheapest?</span>{" "}
          {report.narrative.whyNotCheapest}
        </p>
      )}
    </section>
  );
}

function Card({
  heading,
  vendorName,
  total,
  detail,
  highlight,
}: {
  heading: string;
  vendorName: string;
  total?: number;
  detail: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={
        "rounded-xl border p-4 " +
        (highlight
          ? "border-verified/40 bg-verified-soft"
          : "border-border bg-surface-muted")
      }
    >
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {heading}
      </div>
      <div className="mt-1 flex items-baseline justify-between gap-3">
        <span className="font-medium">{vendorName}</span>
        <span className="text-lg font-semibold tabular-nums">{usd(total)}</span>
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
    </div>
  );
}
