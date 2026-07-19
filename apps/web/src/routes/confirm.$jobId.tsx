import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { JobSpecSummary } from "@/components/veramove/JobSpecSummary";
import { MissingFieldAlert } from "@/components/veramove/MissingFieldAlert";
import { ErrorState, LoadingState } from "@/components/veramove/States";
import { useConfirmJob, useJob, useUpdateJob } from "@/lib/api/hooks";
import { runtimeMode } from "@/api/client";
import { ApiError } from "@/api/client";
import type { JobView, JobViewState } from "@/lib/api/types";
import { AlertTriangle, ArrowRight, Lock, PhoneCall, RefreshCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

export const Route = createFileRoute("/confirm/$jobId")({
  head: () => ({
    meta: [
      { title: "Confirm move · VeraMove" },
      {
        name: "description",
        content:
          "Review and lock your move specification before VeraMove calls vendors.",
      },
    ],
  }),
  component: ConfirmPage,
});

// Statuses where intake edits are no longer allowed.
const LOCKED_STATES = new Set<JobViewState>([
  "confirmed",
  "calling",
  "quotes_ready",
  "negotiating",
  "completed",
]);

// Statuses where the workflow has moved past confirmation entirely —
// we should send the user forward, not offer them a Confirm button.
const PAST_CONFIRM_STATES = new Set<JobViewState>([
  "calling",
  "quotes_ready",
  "negotiating",
  "completed",
]);

function ConfirmPage() {
  const { jobId } = Route.useParams();
  const navigate = useNavigate();
  const jobQ = useJob(jobId);
  const update = useUpdateJob();
  const confirm = useConfirmJob();

  // Local working copy so users can edit fields without hammering the server.
  const [draft, setDraft] = useState<JobView | null>(null);
  const [ack, setAck] = useState(false);
  const [creatingRevision, setCreatingRevision] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  useEffect(() => {
    if (jobQ.data) setDraft(jobQ.data);
  }, [jobQ.data]);

  const isLocked = !!draft?.confirmedAt || (draft ? LOCKED_STATES.has(draft.status) : false);
  const isFailed = draft?.status === "failed";
  const pastConfirm = draft ? PAST_CONFIRM_STATES.has(draft.status) : false;

  // Recompute missing fields whenever the draft changes so the block updates live.
  const effectiveMissing = useMemo(() => {
    if (!draft) return [] as string[];
    const missing = new Set(draft.missingFields ?? []);
    if (draft.access.longCarryFt > 0) missing.delete("access.longCarryFt");
    if (draft.move.flexibilityDays >= 0 && !Number.isNaN(draft.move.flexibilityDays))
      missing.delete("move.flexibilityDays");
    if (!draft.move.originCity || !draft.move.destinationCity) missing.add("move.route");
    else missing.delete("move.route");
    return Array.from(missing);
  }, [draft]);

  if (jobQ.isLoading || !draft) return <LoadingState label="Loading your move spec…" />;
  if (jobQ.isError) {
    const err = jobQ.error;
    const is404 = err instanceof ApiError && err.status === 404;
    return (
      <ErrorState
        title={is404 ? "This move doesn't exist" : "Couldn't load this move"}
        description={
          is404
            ? "The job id in the URL isn't recognised. It may have expired, or you may have followed a stale link."
            : err instanceof ApiError
              ? err.detail
              : "The backend is unreachable. Check the API status in the header and try again."
        }
        onRetry={() => jobQ.refetch()}
      />
    );
  }

  const patchDraft = (patch: Partial<JobView>) => {
    setDraft((d) => {
      if (!d) return d;
      const edited = new Set(d.editedFields ?? []);
      Object.keys(patch).forEach((k) => edited.add(k));
      return { ...d, ...patch, editedFields: Array.from(edited) };
    });
  };

  const hasMissing = effectiveMissing.length > 0;
  const canConfirm = !hasMissing && ack && !isLocked && !isFailed;

  const onConfirm = async () => {
    if (!canConfirm) return;
    setConfirmError(null);
    try {
      // Persist local edits FIRST — but only in demo mode. In live mode there
      // is no PATCH endpoint (see endpoints.ts). Edits round-trip via the demo
      // adapter's in-memory store; live-mode confirmation locks whatever the
      // backend already knows about the spec.
      if (runtimeMode === "demo") {
        await update.mutateAsync({
          jobId: draft.id,
          patch: {
            move: draft.move,
            access: draft.access,
            inventory: draft.inventory,
            services: draft.services,
            extras: draft.extras,
            notes: draft.notes,
            homeType: draft.homeType,
            bedrooms: draft.bedrooms,
            missingFields: effectiveMissing,
            editedFields: draft.editedFields,
          },
        });
      }
      await confirm.mutateAsync(draft.id);
      navigate({ to: "/calls/$jobId", params: { jobId: draft.id } });
    } catch (e) {
      setConfirmError(
        e instanceof ApiError
          ? e.detail
          : e instanceof Error
            ? e.message
            : "Confirmation failed. Try again.",
      );
    }
  };

  const reviseSpec = async () => {
    setCreatingRevision(true);
    try {
      // Frontend-only revise: bumps the version and clears the confirmed
      // stamp so the user can edit again. In live mode this is UI-only — the
      // backend has no dedicated revise endpoint on the canonical route list.
      const revised: JobView = {
        ...draft,
        version: (draft.version ?? 1) + 1,
        status: "intake_complete",
        confirmedAt: undefined,
      };
      if (runtimeMode === "demo") {
        await update.mutateAsync({ jobId: draft.id, patch: revised });
      }
      setDraft(revised);
      setAck(false);
    } finally {
      setCreatingRevision(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Review and confirm
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Once vendor calling begins, these facts cannot change. Every vendor
          receives the same locked specification — that's what keeps the
          quotes comparable.
        </p>
      </header>

      {isFailed && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl border border-risk/40 bg-risk-soft p-4"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 text-risk" aria-hidden />
          <div className="flex-1 text-sm">
            <div className="font-medium text-foreground">
              This move is in a failed state
            </div>
            <p className="text-muted-foreground">
              The backend reported a terminal failure for this job. Start a new
              intake to try again.
            </p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link to="/intake">Start new intake</Link>
          </Button>
        </div>
      )}

      {pastConfirm && !isFailed && (
        <div
          role="status"
          className="flex flex-wrap items-start gap-3 rounded-xl border border-primary/30 bg-primary/5 p-4"
        >
          <ArrowRight className="mt-0.5 h-4 w-4 text-primary" aria-hidden />
          <div className="flex-1 text-sm">
            <div className="font-medium text-foreground">
              This move has already moved past confirmation
            </div>
            <p className="text-muted-foreground">
              Current stage:{" "}
              <span className="font-medium text-foreground">{draft.status.replace("_", " ")}</span>.
              Intake is locked — jump ahead to the current step.
            </p>
          </div>
          <Button asChild size="sm" className="gap-1.5">
            {draft.status === "completed" ? (
              <Link to="/report/$jobId" params={{ jobId: draft.id }}>
                View report <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : draft.status === "negotiating" || draft.status === "quotes_ready" ? (
              <Link to="/negotiate/$jobId" params={{ jobId: draft.id }}>
                Go to negotiation <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <Link to="/calls/$jobId" params={{ jobId: draft.id }}>
                Go to calls <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </Button>
        </div>
      )}

      {hasMissing && !isLocked && (
        <MissingFieldAlert fields={effectiveMissing.map(labelFor)} />
      )}

      {isLocked && !pastConfirm && (
        <div
          role="status"
          className="flex flex-wrap items-start gap-3 rounded-xl border border-verified/30 bg-verified-soft p-4"
        >
          <Lock className="mt-0.5 h-4 w-4 text-verified" aria-hidden />
          <div className="flex-1 text-sm">
            <div className="font-medium text-foreground">
              Specification locked · version {draft.version} in use for vendor calls
            </div>
            <p className="text-muted-foreground">
              To change anything now, create a revised version. This prevents
              silent edits mid-call.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={reviseSpec}
            disabled={creatingRevision}
            className="gap-1.5"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            {creatingRevision ? "Preparing…" : "Create revised version"}
          </Button>
          <Button asChild size="sm" className="gap-1.5">
            <Link to="/calls/$jobId" params={{ jobId: draft.id }}>
              <PhoneCall className="h-3.5 w-3.5" />
              Start calls
            </Link>
          </Button>
        </div>
      )}

      <JobSpecSummary
        job={draft}
        locked={isLocked}
        onChange={patchDraft}
      />

      {!isLocked && !isFailed && (
        <div className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-5">
          <label className="flex items-start gap-3">
            <Checkbox
              id="ack"
              checked={ack}
              onCheckedChange={(v) => setAck(!!v)}
              disabled={hasMissing}
              aria-describedby="ack-desc"
            />
            <span className="text-sm">
              <span className="font-medium">
                I confirm this specification will be used on every vendor call.
              </span>
              <span id="ack-desc" className="mt-0.5 block text-muted-foreground">
                All three movers will receive the exact same details so the
                quotes are directly comparable.
              </span>
            </span>
          </label>

          {hasMissing && (
            <p className="flex items-center gap-1.5 text-sm text-risk">
              <AlertTriangle className="h-4 w-4" aria-hidden />
              Add the missing required fields above before confirming.
            </p>
          )}

          {confirmError && (
            <div
              role="alert"
              aria-live="polite"
              className="flex items-start gap-2 rounded-lg border border-risk/30 bg-risk-soft p-3 text-sm"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-risk" aria-hidden />
              <div className="flex-1">
                <div className="font-medium">Couldn't lock this specification</div>
                <p className="text-muted-foreground">{confirmError}</p>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Ready? We'll start dialing the three movers immediately.
            </p>
            <Button
              size="lg"
              onClick={onConfirm}
              disabled={!canConfirm || confirm.isPending || update.isPending}
              className="gap-1.5"
            >
              {confirm.isPending
                ? "Locking version…"
                : `Confirm and lock version ${draft.version}`}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// Human-readable labels for missing-field keys used in the alert.
function labelFor(key: string): string {
  const map: Record<string, string> = {
    "move.route": "Route (origin & destination)",
    "move.date": "Move date",
    "move.flexibilityDays": "Date flexibility",
    "access.longCarryFt": "Parking / long-carry distance",
    "access.originFloor": "Origin floor",
    "access.destinationFloor": "Destination floor",
    "services.insuranceTier": "Insurance tier",
    "inventory": "Inventory",
    "homeType": "Home type",
  };
  return map[key] ?? key;
}
