import { createFileRoute, Link } from "@tanstack/react-router";
import { useCalls, useJob, useReport } from "@/lib/api/hooks";
import { ReportHero } from "@/components/veramove/ReportHero";
import { CheapestVsBestValue } from "@/components/veramove/CheapestVsBestValue";
import { RankedComparison } from "@/components/veramove/RankedComparison";
import { HiddenFeeWarnings } from "@/components/veramove/HiddenFeeWarnings";
import { NegotiationSummary } from "@/components/veramove/NegotiationSummary";
import { WhyWonNarrative } from "@/components/veramove/WhyWonNarrative";
import { EvidenceBadge } from "@/components/veramove/EvidenceBadge";
import { LoadingState } from "@/components/veramove/States";
import { StatusPill } from "@/components/veramove/StatusPill";
import { ApiError, useRuntimeMode } from "@/api/client";
import { AlertTriangle, ArrowRight, FileText, Sparkles } from "lucide-react";
import type { JobViewState } from "@/lib/api/types";

export const Route = createFileRoute("/report/$jobId")({
  head: () => ({
    meta: [
      { title: "Recommendation · VeraMove" },
      {
        name: "description",
        content:
          "Ranked, evidence-backed moving recommendation with tradeoffs and transcript links.",
      },
    ],
  }),
  component: ReportPage,
});

function ReportPage() {
  const { jobId } = Route.useParams();
  const isDemoMode = useRuntimeMode() === "demo";
  const jobQ = useJob(jobId, { poll: false });
  const status = jobQ.data?.status as JobViewState | undefined;
  // Poll job during negotiating so the report unlocks automatically.
  const jobPollQ = useJob(jobId, { poll: status === "negotiating" });
  const effectiveStatus = (jobPollQ.data?.status ?? status) as JobViewState | undefined;

  const reportQ = useReport(jobId);
  const callsQ = useCalls(jobId);

  if (jobQ.isLoading && !jobQ.data) return <LoadingState label="Loading job…" />;

  // Job-first state gates: never render a fake report because the report
  // endpoint 404'd.
  if (effectiveStatus && effectiveStatus !== "completed") {
    return <StageGate jobId={jobId} status={effectiveStatus} />;
  }

  if (reportQ.isLoading) {
    return <LoadingState label="Building recommendation…" />;
  }

  if (reportQ.isError || !reportQ.data) {
    const err = reportQ.error;
    const message =
      err instanceof ApiError
        ? err.message
        : "The recommendation is not available yet.";
    return (
      <StageGate
        jobId={jobId}
        status={effectiveStatus ?? "confirmed"}
        errorMessage={message}
      />
    );
  }

  const report = reportQ.data;
  const calls = callsQ.data ?? [];
  const synthetic = report.synthetic || isDemoMode;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Ranked recommendation
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every material claim links to a transcript excerpt and a timestamp.
          </p>
        </div>
        {synthetic && (
          <StatusPill
            tone="info"
            icon={<Sparkles className="h-3.5 w-3.5" />}
            className="border-purple-400/40 bg-purple-50 text-purple-900 dark:bg-purple-950/40 dark:text-purple-200"
          >
            Demo · synthetic or role-played
          </StatusPill>
        )}
      </header>

      {synthetic && (
        <div
          role="note"
          className="rounded-xl border border-purple-400/40 bg-purple-50 p-3 text-sm text-purple-900 dark:bg-purple-950/40 dark:text-purple-200"
        >
          Demo vendors and call evidence are synthetic or role-played.
        </div>
      )}

      <ReportHero report={report} calls={calls} />

      <div className="grid gap-6 lg:grid-cols-[1.55fr_1fr]">
        <div className="flex flex-col gap-6">
          <CheapestVsBestValue report={report} />
          <RankedComparison report={report} calls={calls} />
          <NegotiationSummary report={report} calls={calls} />
        </div>
        <div className="flex flex-col gap-6">
          <HiddenFeeWarnings report={report} />
          <EvidenceIndex report={report} jobId={jobId} />
        </div>
      </div>

      <WhyWonNarrative narrative={report.narrative} />

      <footer className="rounded-2xl border border-border bg-surface-muted p-4 text-xs text-muted-foreground">
        VeraMove operates independently today and is designed as a future
        move-in concierge for VeraAI.
        {report.disclaimer ? " " + report.disclaimer : ""}
      </footer>
    </div>
  );
}

function EvidenceIndex({
  report,
  jobId,
}: {
  report: import("@/lib/api/types").ReportView;
  jobId: string;
}) {
  return (
    <section
      aria-labelledby="evidence-index-title"
      className="rounded-2xl border border-border bg-surface p-5"
    >
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <FileText className="h-3.5 w-3.5" aria-hidden />
        Evidence index
      </div>
      <h3 id="evidence-index-title" className="sr-only">
        Evidence index
      </h3>
      {report.evidenceIndex.length === 0 ? (
        <p className="mt-3 text-sm italic text-muted-foreground">
          No evidence links returned for this report.
        </p>
      ) : (
        <ul className="mt-3 space-y-3 text-sm">
          {report.evidenceIndex.map((e) => (
            <li
              key={e.callId}
              className="rounded-lg border border-border p-3"
            >
              <div className="flex items-baseline justify-between gap-2">
                <div className="font-medium">{e.vendorName}</div>
                {e.ts && (
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {e.ts}
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">{e.note}</div>
              <Link
                to="/calls/$jobId"
                params={{ jobId }}
                className="mt-2 inline-block text-xs font-medium text-foreground underline underline-offset-4"
              >
                View transcript
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const STAGE_COPY: Partial<
  Record<
    JobViewState,
    {
      title: string;
      body: string;
      cta?: { label: string; to: "/intake" | "/confirm/$jobId" | "/calls/$jobId" | "/negotiate/$jobId" };
    }
  >
> = {
  draft: {
    title: "Intake is not complete",
    body: "Finish intake before a recommendation can be built.",
    cta: { label: "Return to intake", to: "/intake" },
  },
  intake_complete: {
    title: "Confirm the JobSpec first",
    body: "Confirm and lock the JobSpec so vendors can be called with identical facts.",
    cta: { label: "Review and confirm", to: "/confirm/$jobId" },
  },
  confirmed: {
    title: "Vendor calls are not complete",
    body: "Start the three vendor calls before a recommendation can be built.",
    cta: { label: "Go to Calls", to: "/calls/$jobId" },
  },
  calling: {
    title: "Vendor calls are still in progress",
    body: "The recommendation appears once the three calls finish and quotes are canonicalized.",
    cta: { label: "Watch Calls", to: "/calls/$jobId" },
  },
  quotes_ready: {
    title: "Negotiation is ready",
    body: "Run negotiation to lock in a binding improved total before the recommendation.",
    cta: { label: "Go to negotiation", to: "/negotiate/$jobId" },
  },
  negotiating: {
    title: "Negotiation in progress",
    body: "The recommendation will appear as soon as the negotiation call is materialized. This page refreshes automatically.",
    cta: { label: "Open negotiation", to: "/negotiate/$jobId" },
  },
  failed: {
    title: "This job failed",
    body: "The backend marked this job as failed. See details below.",
  },
};

function StageGate({
  jobId,
  status,
  errorMessage,
}: {
  jobId: string;
  status: JobViewState;
  errorMessage?: string;
}) {
  const copy = STAGE_COPY[status] ?? {
    title: "Recommendation not ready",
    body: "The backend has not produced a report for this job yet.",
  };
  return (
    <section
      role="status"
      aria-live="polite"
      className={
        "rounded-2xl border p-6 " +
        (status === "failed"
          ? "border-risk/30 bg-risk-soft"
          : "border-border bg-surface")
      }
    >
      <div className="flex items-start gap-3">
        <AlertTriangle
          className={
            "mt-1 h-5 w-5 " + (status === "failed" ? "text-risk" : "text-muted-foreground")
          }
          aria-hidden
        />
        <div className="flex-1">
          <h1 className="text-lg font-semibold tracking-tight">{copy.title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{copy.body}</p>
          {errorMessage && (
            <p className="mt-2 rounded-md border border-border bg-surface-muted p-2 text-xs text-muted-foreground">
              {errorMessage}
            </p>
          )}
          {copy.cta && (
            <Link
              to={copy.cta.to}
              params={{ jobId }}
              className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-muted"
            >
              {copy.cta.label}
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
