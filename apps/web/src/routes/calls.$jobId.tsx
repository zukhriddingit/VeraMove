import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useCalls, useEvents, useJob, useStartCalls, useVendorsDiscovery } from "@/lib/api/hooks";
import { jobActions } from "@/lib/api/actions";
import { useRuntimeMode } from "@/api/client";
import { VendorCallCard } from "@/components/veramove/VendorCallCard";
import { QuoteComparison } from "@/components/veramove/QuoteComparison";
import { CallsRequirementsChecklist } from "@/components/veramove/CallsRequirementsChecklist";
import { VendorResearchPanel } from "@/components/veramove/VendorResearchPanel";
import { ErrorState, LoadingState } from "@/components/veramove/States";
import { StatusPill } from "@/components/veramove/StatusPill";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Activity,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  PhoneOutgoing,
  Search,
  Sparkles,
} from "lucide-react";

export const Route = createFileRoute("/calls/$jobId")({
  head: () => ({
    meta: [
      { title: "Vendor calls · VeraMove" },
      {
        name: "description",
        content:
          "Three vendor calls in progress: itemized quotes, hidden-fee discovery, and structured outcomes with transcript evidence.",
      },
    ],
  }),
  component: CallsPage,
});

const ACTIVE_STATES = new Set(["confirmed", "calling", "quotes_ready"] as const);

function CallsPage() {
  const { jobId } = Route.useParams();
  const navigate = useNavigate();
  const isDemoMode = useRuntimeMode() === "demo";

  const jobQ = useJob(jobId, { poll: false });
  const job = jobQ.data;
  const status = job?.status;
  const isActive = !!status && (ACTIVE_STATES as Set<string>).has(status);
  const isCalling = status === "calling";

  // Poll canonical job + calls + events while the job is progressing, and
  // separately during `calling` to catch cascading call updates. Stop once
  // the workflow leaves an active state.
  const jobPollQ = useJob(jobId, { poll: isCalling });
  void jobPollQ;
  const callsQ = useCalls(jobId, { poll: isCalling });
  const eventsQ = useEvents(jobId, { poll: isActive });

  const startCalls = useStartCalls();

  if (jobQ.isLoading) return <LoadingState label="Loading job…" />;
  if (jobQ.isError || !job)
    return <ErrorState title="Couldn't load job" onRetry={() => jobQ.refetch()} />;

  const actions = jobActions(job);
  const calls = callsQ.data ?? [];

  // ── State-driven header CTA ──────────────────────────────────────────────
  let cta: React.ReactNode = null;
  if (actions.canStartCalls && isDemoMode) {
    cta = (
      <Button
        onClick={() => startCalls.mutate(jobId)}
        disabled={startCalls.isPending}
        className="gap-1.5"
      >
        <PhoneOutgoing className="h-4 w-4" />
        {startCalls.isPending ? "Starting calls…" : "Start three vendor calls"}
      </Button>
    );
  } else if (status === "quotes_ready") {
    cta = (
      <Button asChild className="gap-1.5">
        <Link to="/negotiate/$jobId" params={{ jobId }}>
          Continue to negotiation
          <ArrowRight className="h-4 w-4" />
        </Link>
      </Button>
    );
  } else if (status === "negotiating") {
    cta = (
      <Button asChild variant="outline" className="gap-1.5">
        <Link to="/negotiate/$jobId" params={{ jobId }}>
          Go to negotiation
          <ArrowRight className="h-4 w-4" />
        </Link>
      </Button>
    );
  } else if (status === "completed") {
    cta = (
      <Button asChild className="gap-1.5">
        <Link to="/report/$jobId" params={{ jobId }}>
          View recommendation
          <ArrowRight className="h-4 w-4" />
        </Link>
      </Button>
    );
  }

  const stateBanner = renderStateBanner(status, jobId);
  const startError = startCalls.error;

  const median = (() => {
    const totals = calls
      .map((c) => c.verifiedTotal ?? c.headlineQuote ?? 0)
      .filter((n) => n > 0)
      .sort((a, b) => a - b);
    if (totals.length === 0) return undefined;
    const mid = Math.floor(totals.length / 2);
    return totals.length % 2 ? totals[mid] : (totals[mid - 1] + totals[mid]) / 2;
  })();

  const leverageMap = new Map<string, string>();
  calls.forEach((c) =>
    calls.forEach((v) => {
      if (v.id === c.id) return;
      if (c.negotiation && c.negotiation.leverageVendorId === v.vendor.id) {
        leverageMap.set(c.id, v.vendor.name);
      }
    }),
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Vendor calls</h1>
            {job.synthetic && (
              <StatusPill tone="info" icon={<Sparkles className="h-3 w-3" />}>
                Demo · role-play vendors
              </StatusPill>
            )}
          </div>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Three calls using the same locked JobSpec. Every fee, every commitment, and every
            hidden-fee moment is captured for evidence.
          </p>
        </div>
        {cta}
      </header>

      {stateBanner}

      {!isDemoMode && status && !["draft", "intake_complete", "failed"].includes(status) && (
        <VendorResearchPanel
          jobId={jobId}
          onStartCalls={() => startCalls.mutate(jobId)}
          startPending={startCalls.isPending}
          canStartCalls={actions.canStartCalls}
        />
      )}

      {startError && (
        <ErrorState
          title="Couldn't start calls"
          description={(startError as Error).message}
          onRetry={() => startCalls.mutate(jobId)}
        />
      )}

      {actions.canStartCalls && calls.length === 0 && isDemoMode && (
        <section className="rounded-2xl border border-dashed border-border bg-surface-muted p-8 text-center">
          <PhoneOutgoing className="mx-auto h-6 w-6 text-muted-foreground" />
          <h2 className="mt-2 text-base font-semibold">Ready to place three calls</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            The locked spec (version {job.version}) will be sent to every vendor. Nothing about your
            move changes after this point.
          </p>
        </section>
      )}

      {(status === "calling" ||
        status === "quotes_ready" ||
        status === "negotiating" ||
        status === "completed") && (
        <>
          {callsQ.isLoading && calls.length === 0 && (
            <div className="grid gap-4 lg:grid-cols-3">
              <Skeleton className="h-[420px] w-full rounded-2xl" />
              <Skeleton className="h-[420px] w-full rounded-2xl" />
              <Skeleton className="h-[420px] w-full rounded-2xl" />
            </div>
          )}

          {calls.length > 0 && (
            <>
              {calls.some((c) => c.outcome === "itemized_quote") && (
                <QuoteComparison calls={calls} median={median} />
              )}

              <section className="grid gap-4 lg:grid-cols-3">
                {calls.slice(0, 3).map((c) => (
                  <VendorCallCard
                    key={c.id}
                    call={c}
                    leverageVendorName={leverageMap.get(c.id)}
                    synthetic={job.synthetic}
                    liveMaterializationPending={
                      !isDemoMode && c.status === "completed" && !c.outcome
                    }
                  />
                ))}
              </section>

              <CallsRequirementsChecklist calls={calls.slice(0, 3)} />
            </>
          )}
        </>
      )}

      <ActivityLog events={eventsQ.data ?? []} />

      {isDemoMode && <TavilyDiscoverySection enabledByDefault={false} />}

      {/* Mobile-persistent stage summary */}
      {status && (
        <div className="lg:hidden">
          <div className="sticky bottom-4 mx-auto max-w-md rounded-xl border border-border bg-surface p-3 text-xs text-muted-foreground shadow-md">
            Stage: <span className="font-medium text-foreground">{status.replace("_", " ")}</span>
            {status === "quotes_ready" && (
              <button
                type="button"
                onClick={() => navigate({ to: "/negotiate/$jobId", params: { jobId } })}
                className="ml-2 rounded-md bg-foreground px-2 py-1 text-[11px] font-medium text-background"
              >
                Continue →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function renderStateBanner(status: string | undefined, jobId: string) {
  if (!status) return null;
  if (status === "draft" || status === "intake_complete") {
    return (
      <div className="rounded-xl border border-border bg-surface-muted p-4 text-sm">
        This job hasn't been confirmed yet. Vendor calls can't start until the spec is locked.{" "}
        <Link
          to="/confirm/$jobId"
          params={{ jobId }}
          className="font-medium text-foreground underline"
        >
          Go to confirmation
        </Link>
        .
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className="rounded-xl border border-risk/30 bg-risk-soft p-4 text-sm">
        This job ended in a failed state. Only recovery actions supplied by the backend are
        available.
      </div>
    );
  }
  return null;
}

function ActivityLog({
  events,
}: {
  events: Array<{ ts: string; message: string; type?: string }>;
}) {
  if (events.length === 0) return null;
  // De-duplicate by ts+type to avoid duplicate renders across polls.
  const seen = new Set<string>();
  const rows = events.filter((e) => {
    const k = `${e.ts}|${e.type ?? ""}|${e.message}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  return (
    <section className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Activity className="h-3.5 w-3.5" />
        Activity
      </div>
      <ol className="mt-3 space-y-1.5 text-sm">
        {rows.map((e, i) => (
          <li key={i} className="grid grid-cols-[64px_1fr] gap-3">
            <span className="tabular-nums text-xs text-muted-foreground">{e.ts}</span>
            <span className="text-foreground/90">{e.message}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function TavilyDiscoverySection({ enabledByDefault }: { enabledByDefault: boolean }) {
  const [open, setOpen] = useState(enabledByDefault);
  const q = useVendorsDiscovery(open);
  return (
    <section className="rounded-2xl border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 p-5 text-left"
      >
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <div>
            <div className="text-sm font-semibold">Where a production call list comes from</div>
            <div className="text-xs text-muted-foreground">
              Discovery candidates · not called in this demonstration
            </div>
          </div>
        </div>
        {open ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>
      {open && (
        <div className="border-t border-border p-5 pt-4 text-sm">
          {q.isLoading && <p className="text-muted-foreground">Loading candidates…</p>}
          {q.isError && <p className="text-muted-foreground">Discovery unavailable right now.</p>}
          {q.data && q.data.length > 0 && (
            <>
              <p className="mb-3 text-xs text-muted-foreground">
                Vendors surfaced by discovery for a live production run. These are separate from the
                three role-play counterparties above and are not called in this demonstration.
              </p>
              <ul className="grid gap-2 md:grid-cols-2">
                {q.data.map((v) => (
                  <li
                    key={v.id}
                    className="flex items-center justify-between rounded-lg border border-border bg-surface-muted px-3 py-2"
                  >
                    <span className="text-sm">{v.name}</span>
                    <StatusPill tone="neutral">Discovery</StatusPill>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
