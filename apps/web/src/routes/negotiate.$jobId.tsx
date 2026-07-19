import { createFileRoute, Link } from "@tanstack/react-router";
import { useCalls, useEvents, useJob, useNegotiate } from "@/lib/api/hooks";
import { isDemoMode } from "@/lib/api";
import { setRuntimeMode } from "@/api/client";
import { jobActions } from "@/lib/api/actions";
import { ErrorState, LoadingState } from "@/components/veramove/States";
import { NegotiationPreflight } from "@/components/veramove/NegotiationPreflight";
import { NegotiationProgress } from "@/components/veramove/NegotiationProgress";
import { NegotiationResult } from "@/components/veramove/NegotiationResult";
import { StatusPill } from "@/components/veramove/StatusPill";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/api/client";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Handshake,
  PhoneCall,
} from "lucide-react";

export const Route = createFileRoute("/negotiate/$jobId")({
  head: () => ({
    meta: [
      { title: "Negotiate · VeraMove" },
      {
        name: "description",
        content:
          "Return to one vendor with verified competing leverage and negotiate a measurable improvement.",
      },
    ],
  }),
  component: NegotiatePage,
});

function NegotiatePage() {
  const { jobId } = Route.useParams();
  const demo = isDemoMode;

  const jobQ = useJob(jobId);
  const job = jobQ.data;
  const status = job?.status;

  // Poll while negotiating so we catch the async completion.
  const isNegotiating = status === "negotiating";
  useJob(jobId, { poll: isNegotiating });

  const callsQ = useCalls(jobId);
  const eventsQ = useEvents(jobId, { poll: isNegotiating });

  const negotiate = useNegotiate();

  if (jobQ.isLoading) return <LoadingState label="Loading job…" />;
  if (jobQ.isError || !job) {
    return (
      <ErrorState
        title="Couldn't load job"
        description={jobQ.error instanceof Error ? jobQ.error.message : undefined}
        onRetry={() => jobQ.refetch()}
      />
    );
  }

  const actions = jobActions(job);
  const calls = callsQ.data ?? [];
  const events = eventsQ.data ?? [];

  // Find the target and leverage calls from completed data, without making
  // the frontend responsible for selecting them.
  const targetCall = calls.find((c) => c.negotiation);
  const negotiation = targetCall?.negotiation;
  const leverageCall = negotiation
    ? calls.find((c) => c.vendor.id === negotiation.leverageVendorId)
    : undefined;

  return (
    <div className="flex flex-col gap-6">
      <Header job={job} />

      {/* State-driven body */}
      {status === "confirmed" && (
        <UnavailablePanel
          title="Negotiation opens after the three vendor calls"
          description="Kick off the calling stage first. Once all three quotes are back, VeraMove uses the strongest verified competitor as leverage."
          action={
            <Button asChild variant="secondary">
              <Link to="/calls/$jobId" params={{ jobId }}>
                <ArrowLeft className="mr-1.5 h-4 w-4" />
                Back to calls
              </Link>
            </Button>
          }
        />
      )}

      {status === "calling" && (
        <UnavailablePanel
          title="Waiting for all three quote calls"
          description="Negotiation begins once every vendor has returned a structured outcome. You can watch progress on the calls dashboard."
          action={
            <Button asChild variant="secondary">
              <Link to="/calls/$jobId" params={{ jobId }}>
                <PhoneCall className="mr-1.5 h-4 w-4" />
                View calls in progress
              </Link>
            </Button>
          }
        />
      )}

      {status === "quotes_ready" && (
        <>
          <NegotiationPreflight job={job} calls={calls} demo={demo} />

          <div className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-5 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm font-medium">Start negotiation</div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                One outbound negotiation call using the locked JobSpec v{job.version}.
                {!demo &&
                  " Live materialization of canonical evidence may lag the controlled call."}
              </p>
            </div>
            <Button
              onClick={() => negotiate.mutate(jobId)}
              disabled={!actions.canNegotiate || negotiate.isPending}
              className="gap-1.5"
            >
              <Handshake className="h-4 w-4" />
              {negotiate.isPending ? "Starting…" : "Start negotiation"}
            </Button>
          </div>

          {negotiate.isError && <NegotiationError error={negotiate.error} />}
        </>
      )}

      {status === "negotiating" && (
        <>
          <NegotiationProgress events={events} demo={demo} />
          {!demo && (
            <p className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              The controlled call was initiated, but canonical negotiation
              evidence is not yet available.{" "}
              <button
                type="button"
                onClick={() => setRuntimeMode("demo", { redirectTo: `/negotiate/${jobId}` })}
                className="font-medium text-foreground hover:underline"
              >
                Switch to Demo Mode
              </button>{" "}
              to walk through a fully materialized example.
            </p>
          )}
        </>
      )}

      {status === "completed" && (
        <>
          {negotiation ? (
            <NegotiationResult
              negotiation={negotiation}
              targetCall={targetCall}
              leverageCall={leverageCall}
              demo={demo}
            />
          ) : (
            <UnavailablePanel
              title="Negotiation completed"
              description="The backend marked negotiation complete but did not return a structured result. Continue to the evidence-backed recommendation."
            />
          )}
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button asChild variant="secondary">
              <Link to="/calls/$jobId" params={{ jobId }}>
                <ArrowLeft className="mr-1.5 h-4 w-4" />
                Back to calls
              </Link>
            </Button>
            <Button asChild className="gap-1.5">
              <Link to="/report/$jobId" params={{ jobId }}>
                View evidence-backed recommendation
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </>
      )}

      {status === "failed" && (
        <div
          role="alert"
          className="rounded-2xl border border-risk/40 bg-risk-soft p-5"
        >
          <div className="flex items-center gap-2 text-sm font-semibold">
            <AlertTriangle className="h-4 w-4 text-risk" />
            Backend reported the job as failed
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Negotiation cannot proceed. Review call outcomes for the failure
            details, then restart the workflow from intake if needed.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button asChild variant="secondary">
              <Link to="/calls/$jobId" params={{ jobId }}>
                Back to calls
              </Link>
            </Button>
            <Button asChild variant="secondary">
              <Link to="/intake">Restart intake</Link>
            </Button>
          </div>
        </div>
      )}

      {(status === "draft" || status === "intake_complete") && (
        <UnavailablePanel
          title="Confirm the JobSpec before negotiating"
          description="Negotiation depends on a locked JobSpec and three completed vendor calls."
          action={
            <Button asChild variant="secondary">
              <Link to="/confirm/$jobId" params={{ jobId }}>
                Go to confirmation
              </Link>
            </Button>
          }
        />
      )}
    </div>
  );
}

function Header({ job }: { job: NonNullable<ReturnType<typeof useJob>["data"]> }) {
  return (
    <header className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone="info">JobSpec v{job.version} locked</StatusPill>
        <StatusPill tone="neutral">Status: {job.status.replace("_", " ")}</StatusPill>
        {isDemoMode ? <StatusPill tone="info">Role-play</StatusPill> : null}
      </div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Negotiate</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Return to one vendor with a verified competing quote as leverage.
          Inventory and job facts are locked — only price and inclusions move.
        </p>
      </div>
    </header>
  );
}

function UnavailablePanel({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border bg-surface p-6">
      <div className="text-sm font-semibold">{title}</div>
      <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </section>
  );
}

function NegotiationError({ error }: { error: unknown }) {
  const msg =
    error instanceof ApiError
      ? error.detail || error.message
      : error instanceof Error
        ? error.message
        : "Unknown error";
  return (
    <div
      role="alert"
      className="rounded-xl border border-risk/40 bg-risk-soft p-4 text-sm"
    >
      <div className="flex items-center gap-2 font-medium">
        <AlertTriangle className="h-4 w-4 text-risk" />
        Couldn't start negotiation
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{msg}</p>
    </div>
  );
}
