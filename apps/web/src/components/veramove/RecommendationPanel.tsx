import type { ReportView } from "@/lib/api";
import { usd } from "@/lib/format";
import { Award, ShieldCheck } from "lucide-react";
import { StatusPill } from "./StatusPill";

export function RecommendationPanel({ report }: { report: ReportView }) {
  const rec = report.recommended;
  const top = report.ranking.find((r) => r.vendorId === rec.vendorId);
  if (!top) return null;
  return (
    <section className="rounded-2xl border border-verified/30 bg-verified-soft p-6">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-verified">
        <Award className="h-4 w-4" />
        Recommended with evidence
      </div>
      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-2xl font-semibold tracking-tight">
          {top.vendorName}
        </h2>
        <StatusPill tone="verified" icon={<ShieldCheck className="h-3.5 w-3.5" />}>
          {rec.label}
        </StatusPill>
      </div>
      <div className="mt-2 flex flex-wrap items-baseline gap-3 text-sm">
        <span className="text-lg font-semibold tabular-nums">
          {usd(top.finalTotal)}
        </span>
        <span className="text-muted-foreground">
          {top.binding ? "Binding" : "Non-binding"}
          {top.score !== undefined ? ` · Score ${top.score}/100` : ""}
        </span>
      </div>
      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
        {top.reasons.map((r, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-verified" />
            {r}
          </li>
        ))}
      </ul>
      {rec.tradeoffs.length > 0 && (
        <div className="mt-4 rounded-lg border border-border bg-surface p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Tradeoffs
          </div>
          <ul className="mt-2 space-y-1.5 text-sm text-foreground/90">
            {rec.tradeoffs.map((t, i) => (
              <li key={i}>• {t}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export function RankingList({ report }: { report: ReportView }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <h3 className="text-base font-semibold">Full ranking</h3>
      <ol className="mt-3 space-y-3">
        {report.ranking.map((r, i) => (
          <li key={r.vendorId} className="rounded-xl border border-border p-4">
            <div className="flex items-baseline justify-between gap-3">
              <div className="flex items-baseline gap-2">
                <span className="text-xs text-muted-foreground">#{i + 1}</span>
                <span className="font-medium">{r.vendorName}</span>
              </div>
              <div className="text-sm tabular-nums">
                {usd(r.finalTotal)}{" "}
                {r.score !== undefined && (
                  <span className="text-xs text-muted-foreground">
                    · {r.score}/100
                  </span>
                )}
              </div>
            </div>
            <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
              {r.reasons.map((x, j) => (
                <li key={j}>• {x}</li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
