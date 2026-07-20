import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { JobSpecSummary } from "@/components/veramove/JobSpecSummary";
import { MissingFieldAlert } from "@/components/veramove/MissingFieldAlert";
import { ErrorState, LoadingState } from "@/components/veramove/States";
import { useConfirmJob, useJob, useUpdateJob } from "@/lib/api/hooks";
import { ApiError, useRuntimeMode } from "@/api/client";
import type { JobView, JobViewState } from "@/lib/api/types";
import { AlertTriangle, ArrowRight, Lock, PhoneCall, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";

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
  const runtimeMode = useRuntimeMode();
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

  const effectiveMissing = draft?.missingFields ?? [];

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

  const patchDraft = (patch: Partial<JobView>, fieldKey?: string) => {
    setDraft((d) => {
      if (!d) return d;
      const next = { ...d, ...patch };
      const edited = new Set(d.editedFields ?? []);
      if (fieldKey) edited.add(fieldKey);
      else Object.keys(patch).forEach((key) => edited.add(key));
      const missing = new Set(next.missingFields ?? []);
      if (fieldKey && REQUIRED_REVIEW_FIELDS.has(fieldKey)) {
        if (reviewFieldIsComplete(next, fieldKey)) missing.delete(fieldKey);
        else missing.add(fieldKey);
      }
      return {
        ...next,
        editedFields: Array.from(edited),
        missingFields: Array.from(missing),
      };
    });
  };

  const restoreDraft = (snapshot: JobView) => setDraft(snapshot);
  const reviewPatch = (currentDraft: JobView): Partial<JobView> => ({
    move: currentDraft.move,
    access: currentDraft.access,
    inventory: currentDraft.inventory,
    services: currentDraft.services,
    extras: currentDraft.extras,
    notes: currentDraft.notes,
    homeType: currentDraft.homeType,
    bedrooms: currentDraft.bedrooms,
    missingFields: currentDraft.missingFields,
    editedFields: currentDraft.editedFields,
  });

  const commitField = async (fieldKey: string) => {
    const nextMissing = new Set(draft.missingFields ?? []);
    if (REQUIRED_REVIEW_FIELDS.has(fieldKey)) {
      if (reviewFieldIsComplete(draft, fieldKey)) nextMissing.delete(fieldKey);
      else nextMissing.add(fieldKey);
    }
    const reviewedDraft = {
      ...draft,
      missingFields: Array.from(nextMissing),
    };
    const saved = await update.mutateAsync({
      jobId: reviewedDraft.id,
      patch: reviewPatch(reviewedDraft),
    });
    setDraft(saved);
    setAck(false);
  };

  const hasMissing = effectiveMissing.length > 0;
  const canConfirm = !hasMissing && ack && !isLocked && !isFailed;

  const onConfirm = async () => {
    if (!canConfirm) return;
    setConfirmError(null);
    try {
      // Always persist the reviewed draft before locking it. The live adapter
      // writes a generated JobSpecV1 through PUT /api/jobs/{job_id}; the demo
      // adapter stores the same review shape locally.
      await update.mutateAsync({
        jobId: draft.id,
        patch: reviewPatch({ ...draft, missingFields: effectiveMissing }),
      });
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
        onRestore={restoreDraft}
        onCommit={commitField}
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

function reviewFieldIsComplete(job: JobView, key: string): boolean {
  switch (key) {
    case "move.route":
      return Boolean(job.move.originCity.trim() && job.move.destinationCity.trim());
    case "move.date":
      return /^\d{4}-\d{2}-\d{2}$/.test(job.move.date);
    case "move.flexibilityDays":
      return Number.isFinite(job.move.flexibilityDays) && job.move.flexibilityDays >= 0;
    case "homeType":
      return Boolean(job.homeType.trim()) && job.bedrooms !== undefined && job.bedrooms >= 0;
    case "access.origin":
      return Number.isFinite(job.access.originFloor) && job.access.originFloor >= 0;
    case "access.destination":
      return Number.isFinite(job.access.destinationFloor) && job.access.destinationFloor >= 0;
    case "access.longCarryFt":
      return Number.isFinite(job.access.longCarryFt) && job.access.longCarryFt >= 0;
    case "inventory":
      return job.inventory.length > 0 && job.inventory.every((item) =>
        Boolean(item.item.trim()) && Number.isFinite(item.qty) && item.qty >= 1);
    case "services.packing":
      return typeof job.services.packing === "boolean";
    case "extras.disassembly":
      return typeof job.extras?.disassembly === "boolean";
    case "extras.storage":
      return typeof job.extras?.storage === "boolean";
    case "services.insuranceTier":
      return job.services.insuranceTier === "standard" || job.services.insuranceTier === "full-value";
    default:
      return true;
  }
}

const REQUIRED_REVIEW_FIELDS = new Set([
  "move.route",
  "move.date",
  "move.flexibilityDays",
  "homeType",
  "access.origin",
  "access.destination",
  "access.longCarryFt",
  "inventory",
  "services.packing",
  "extras.disassembly",
  "extras.storage",
  "services.insuranceTier",
]);

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
