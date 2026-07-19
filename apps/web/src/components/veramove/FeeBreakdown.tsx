import type { FeeItemView } from "@/lib/api";
import { usd } from "@/lib/format";
import { Eye } from "lucide-react";

export function FeeBreakdown({
  fees,
  hiddenFees,
  total,
}: {
  fees: FeeItemView[];
  hiddenFees?: FeeItemView[];
  total?: number;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Fee breakdown
      </div>
      <ul className="mt-2 space-y-1.5 text-sm">
        {fees.map((f, i) => (
          <li key={i} className="flex items-baseline justify-between gap-4">
            <span className="text-foreground">{f.label}</span>
            <span className="tabular-nums text-foreground">{usd(f.amount)}</span>
          </li>
        ))}
        {hiddenFees?.map((f, i) => (
          <li key={`h-${i}`} className="flex items-baseline justify-between gap-4">
            <span className="flex items-center gap-1.5 text-caution-foreground">
              <Eye className="h-3.5 w-3.5" />
              {f.label}
            </span>
            <span className="tabular-nums text-caution-foreground">
              {usd(f.amount)}
            </span>
          </li>
        ))}
      </ul>
      {total !== undefined && (
        <div className="mt-3 flex items-baseline justify-between border-t border-border/70 pt-3 text-sm font-semibold">
          <span>Verified total</span>
          <span className="tabular-nums">{usd(total)}</span>
        </div>
      )}
    </div>
  );
}
