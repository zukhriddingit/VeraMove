import type { CallView } from "@/lib/api";
import { usd } from "@/lib/format";

export function QuoteComparison({
  calls,
  median,
}: {
  calls: CallView[];
  median?: number;
}) {
  const totals = calls
    .map((c) => c.verifiedTotal ?? c.headlineQuote ?? 0)
    .filter((n) => n > 0);
  const max = Math.max(...totals, 1);
  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-base font-semibold">Quote comparison</h3>
        {median !== undefined && (
          <span className="text-xs text-muted-foreground">
            Comparison median · <span className="tabular-nums text-foreground">{usd(median)}</span>
          </span>
        )}
      </div>
      <ul className="mt-4 space-y-3">
        {calls.map((c) => {
          const value = c.verifiedTotal ?? c.headlineQuote ?? 0;
          const pct = Math.round((value / max) * 100);
          return (
            <li key={c.id}>
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-medium">{c.vendor.name}</span>
                <span className="tabular-nums">
                  {usd(value)}{" "}
                  <span className="text-xs text-muted-foreground">
                    {c.binding ? "binding" : "non-binding"}
                  </span>
                </span>
              </div>
              <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={
                    "h-full " +
                    (c.binding ? "bg-verified" : "bg-caution")
                  }
                  style={{ width: `${pct}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
