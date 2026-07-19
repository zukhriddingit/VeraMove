import type { FeeItemView, RedFlagView } from "@/lib/api";
import { usd } from "@/lib/format";
import { AlertTriangle, EyeOff } from "lucide-react";

export function HiddenFeeAlert({ fees }: { fees: FeeItemView[] }) {
  if (fees.length === 0) return null;
  const total = fees.reduce((s, f) => s + f.amount, 0);
  return (
    <div className="rounded-xl border border-caution/40 bg-caution-soft p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-caution-foreground">
        <EyeOff className="h-4 w-4" />
        {fees.length} fee{fees.length === 1 ? "" : "s"} surfaced only after questioning · {usd(total)}
      </div>
      <ul className="mt-2 space-y-0.5 text-xs text-caution-foreground/85">
        {fees.map((f, i) => (
          <li key={i}>
            {f.label} — {usd(f.amount)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RedFlagAlert({ flags }: { flags: RedFlagView[] }) {
  if (flags.length === 0) return null;
  return (
    <ul className="space-y-2">
      {flags.map((f) => {
        const risk = f.severity === "risk";
        return (
          <li
            key={f.id}
            className={
              "flex items-start gap-2 rounded-xl border p-3 text-sm " +
              (risk
                ? "border-risk/30 bg-risk-soft text-foreground"
                : "border-caution/40 bg-caution-soft text-caution-foreground")
            }
          >
            <AlertTriangle
              className={"mt-0.5 h-4 w-4 " + (risk ? "text-risk" : "")}
            />
            <div>
              <div className="font-medium">{f.message}</div>
              {f.evidence && (
                <div className="mt-0.5 text-xs opacity-80">
                  Evidence · {f.evidence.ts} — “{f.evidence.excerpt}”
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
