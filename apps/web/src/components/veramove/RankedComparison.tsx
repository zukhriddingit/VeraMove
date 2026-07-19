import type { RankedVendorView, ReportView, CallView } from "@/lib/api/types";
import { usd } from "@/lib/format";
import { EvidenceBadge } from "./EvidenceBadge";
import { ItemizedVendorDrawer } from "./ItemizedVendorDrawer";
import { ChevronDown } from "lucide-react";

/**
 * Renders the backend-supplied ranking. Order is preserved as-returned —
 * the frontend never reorders, re-scores, or re-labels.
 */
export function RankedComparison({
  report,
  calls,
}: {
  report: ReportView;
  calls: CallView[];
}) {
  const callFor = (vendorId: string) =>
    calls.find((c) => c.vendor.id === vendorId);

  return (
    <section
      aria-labelledby="ranking-title"
      className="rounded-2xl border border-border bg-surface p-5"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 id="ranking-title" className="text-base font-semibold">
          Ranked comparison
        </h3>
        {report.medianVerifiedTotal !== undefined && (
          <span className="text-xs text-muted-foreground">
            Comparison median ·{" "}
            <span className="tabular-nums text-foreground">
              {usd(report.medianVerifiedTotal)}
            </span>
          </span>
        )}
      </div>

      {/* Mobile: stacked cards */}
      <ol className="mt-4 space-y-3 lg:hidden">
        {report.ranking.map((r, i) => (
          <li key={r.vendorId}>
            <RankCard rank={i + 1} vendor={r} call={callFor(r.vendorId)} />
          </li>
        ))}
      </ol>

      {/* Desktop: table + per-row drawer */}
      <div className="mt-4 hidden lg:block">
        <div className="grid grid-cols-[36px_1.4fr_1fr_1fr_1fr_0.9fr_36px] items-center gap-3 border-b border-border pb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          <span>#</span>
          <span>Vendor</span>
          <span className="text-right">Headline</span>
          <span className="text-right">Verified</span>
          <span className="text-right">Negotiated</span>
          <span>State</span>
          <span className="sr-only">Expand</span>
        </div>
        <ol>
          {report.ranking.map((r, i) => (
            <RankRow
              key={r.vendorId}
              rank={i + 1}
              vendor={r}
              call={callFor(r.vendorId)}
            />
          ))}
        </ol>
      </div>
    </section>
  );
}

function fmt(n?: number) {
  return n === undefined || n === null ? "Not provided" : usd(n);
}

function RankRow({
  rank,
  vendor,
  call,
}: {
  rank: number;
  vendor: RankedVendorView;
  call?: CallView;
}) {
  return (
    <li className="border-b border-border last:border-b-0">
      <details className="group">
        <summary className="grid cursor-pointer grid-cols-[36px_1.4fr_1fr_1fr_1fr_0.9fr_36px] items-center gap-3 py-3 text-sm">
          <span className="text-muted-foreground">#{rank}</span>
          <span className="flex flex-col">
            <span className="flex items-center gap-2 font-medium">
              {vendor.vendorName}
              {vendor.label && (
                <span className="rounded-full border border-border bg-surface-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {vendor.label}
                </span>
              )}
            </span>
            <span className="text-xs text-muted-foreground">
              {vendor.binding ? "Binding" : "Non-binding"}
              {vendor.availability ? ` · ${vendor.availability}` : ""}
            </span>
          </span>
          <span className="text-right tabular-nums">{fmt(vendor.headlineTotal)}</span>
          <span className="text-right tabular-nums">{fmt(vendor.verifiedTotal)}</span>
          <span className="text-right tabular-nums">{fmt(vendor.negotiatedTotal)}</span>
          <span>
            <EvidenceBadge state={vendor.verificationState} synthetic={vendor.synthetic} />
          </span>
          <ChevronDown
            className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180"
            aria-hidden
          />
        </summary>
        <div className="pb-4">
          <ItemizedVendorDrawer vendor={vendor} call={call} />
        </div>
      </details>
    </li>
  );
}

function RankCard({
  rank,
  vendor,
  call,
}: {
  rank: number;
  vendor: RankedVendorView;
  call?: CallView;
}) {
  return (
    <details className="group rounded-xl border border-border bg-surface-muted p-4">
      <summary className="cursor-pointer list-none">
        <div className="flex items-baseline justify-between gap-3">
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-muted-foreground">#{rank}</span>
            <span className="font-medium">{vendor.vendorName}</span>
          </div>
          <span className="text-sm font-semibold tabular-nums">
            {fmt(vendor.negotiatedTotal ?? vendor.verifiedTotal ?? vendor.finalTotal)}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {vendor.label && (
            <span className="rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {vendor.label}
            </span>
          )}
          <EvidenceBadge state={vendor.verificationState} synthetic={vendor.synthetic} />
          <span className="text-xs text-muted-foreground">
            {vendor.binding ? "Binding" : "Non-binding"}
          </span>
        </div>
      </summary>
      <div className="mt-3">
        <ItemizedVendorDrawer vendor={vendor} call={call} />
      </div>
    </details>
  );
}
