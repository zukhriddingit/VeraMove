import type { ReportView, CallView } from "@/lib/api/types";
import { usd } from "@/lib/format";
import { Award, TrendingDown, Calendar, ShieldCheck, FileCheck2 } from "lucide-react";
import { EvidenceBadge } from "./EvidenceBadge";
import { StatusPill } from "./StatusPill";

/**
 * ReportView hero — renders the backend's recommended vendor. Never runs its
 * own ranking; a missing recommendation is shown honestly instead.
 */
export function ReportHero({
  report,
  calls,
}: {
  report: ReportView;
  calls: CallView[];
}) {
  const rec = report.recommended;
  const top = report.ranking.find((r) => r.vendorId === rec.vendorId);
  const call = calls.find((c) => c.vendor.id === rec?.vendorId);
  if (!top) {
    return (
      <section className="rounded-2xl border border-border bg-surface p-6">
        <p className="text-sm text-muted-foreground">
          The backend has not returned a recommended vendor for this job yet.
        </p>
      </section>
    );
  }
  const finalTotal = top.negotiatedTotal ?? top.verifiedTotal ?? top.finalTotal;
  const savings =
    typeof top.headlineTotal === "number" && typeof top.negotiatedTotal === "number"
      ? top.headlineTotal - top.negotiatedTotal
      : rec.savingsVsHighest;

  return (
    <section className="rounded-2xl border border-verified/30 bg-verified-soft p-6 lg:p-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-verified">
          <Award className="h-4 w-4" aria-hidden />
          Recommended with evidence
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <EvidenceBadge state={top.verificationState} synthetic={top.synthetic} />
          {typeof top.evidenceCount === "number" && (
            <StatusPill tone="info" icon={<FileCheck2 className="h-3.5 w-3.5" />}>
              {top.evidenceCount} evidence link{top.evidenceCount === 1 ? "" : "s"}
            </StatusPill>
          )}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-2xl font-semibold tracking-tight lg:text-3xl">
          {top.vendorName}
        </h2>
        <span className="rounded-full border border-verified/40 bg-white/60 px-3 py-1 text-xs font-medium text-foreground">
          {rec.label}
        </span>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Stat
          label="Final verified total"
          value={usd(finalTotal)}
          hint={top.binding ? "Binding" : "Non-binding"}
        />
        <Stat
          label="Negotiated savings"
          value={savings > 0 ? `- ${usd(savings)}` : "—"}
          hint={
            top.negotiatedTotal !== undefined && top.headlineTotal !== undefined
              ? `From ${usd(top.headlineTotal)}`
              : "Backend-reported"
          }
          icon={savings > 0 ? <TrendingDown className="h-3.5 w-3.5 text-verified" /> : undefined}
        />
        <Stat
          label="Availability"
          value={top.availability ?? "Awaiting verification"}
          hint={top.deposit !== undefined ? `Deposit ${usd(top.deposit)}` : "Deposit not provided"}
          icon={<Calendar className="h-3.5 w-3.5 text-muted-foreground" />}
        />
      </div>

      {report.narrative?.whyThisVendor ? (
        <p className="mt-5 text-sm leading-relaxed text-foreground/90">
          {report.narrative.whyThisVendor}
        </p>
      ) : (
        <ul className="mt-5 grid gap-2 sm:grid-cols-2">
          {top.reasons.map((r, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-verified" aria-hidden />
              {r}
            </li>
          ))}
        </ul>
      )}

      {call?.recording?.url ? null : (
        <p className="mt-3 text-xs text-muted-foreground">
          Call recording{call ? "" : " for this vendor"} is not available.
        </p>
      )}
    </section>
  );
}

function Stat({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: string;
  hint?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-xl font-semibold tabular-nums">{value}</span>
      </div>
      {hint && (
        <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          {icon}
          <span>{hint}</span>
        </div>
      )}
    </div>
  );
}
