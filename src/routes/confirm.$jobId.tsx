import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type JobRecord, type LocationSpec } from "@/lib/api";
import { ErrorBox, LoadingCard, Stepper } from "@/components/flow";

export const Route = createFileRoute("/confirm/$jobId")({
  head: () => ({
    meta: [
      { title: "Confirm spec — VeraMove" },
      { name: "description", content: "Review and lock the move specification." },
    ],
  }),
  component: ConfirmPage,
});

function ConfirmPage() {
  const { jobId } = useParams({ from: "/confirm/$jobId" });
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId),
  });

  const confirmMut = useMutation({
    mutationFn: () => api.confirmJob(jobId),
    onSuccess: (job) => qc.setQueryData(["job", jobId], job),
  });

  if (isLoading)
    return (
      <div className="space-y-6">
        <Stepper current="confirm" jobId={jobId} />
        <LoadingCard label="Loading job…" />
      </div>
    );
  if (error)
    return (
      <div className="space-y-6">
        <Stepper current="confirm" jobId={jobId} />
        <ErrorBox message={(error as Error).message} />
      </div>
    );
  if (!data) return null;

  const job = data;
  const spec = job.job_spec;
  const isLocked = spec.confirmed || job.state !== "intake_complete";

  return (
    <div className="space-y-8">
      <Stepper current="confirm" jobId={jobId} />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground">Step 2 · Confirm spec</div>
          <h1 className="mt-1 font-display text-4xl text-ink">Review your move</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Job <code className="rounded bg-muted px-1 py-0.5 text-xs">{spec.job_id}</code> · state{" "}
            <StatePill state={job.state} />
          </p>
        </div>
        {isLocked ? (
          <Link
            to="/calls/$jobId"
            params={{ jobId }}
            className="rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
          >
            Go to vendor calls →
          </Link>
        ) : (
          <button
            onClick={() => confirmMut.mutate()}
            disabled={confirmMut.isPending}
            className="rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
          >
            {confirmMut.isPending ? "Locking…" : "Confirm & lock spec"}
          </button>
        )}
      </header>

      {confirmMut.error && (
        <ErrorBox message={(confirmMut.error as Error).message} />
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Move details">
          <Row label="Move date" value={`${spec.move_date} ${spec.date_flexible ? "(flexible)" : "(fixed)"}`} />
          <Row label="Bedrooms" value={String(spec.bedroom_count)} />
          <Row label="Insurance" value={spec.insurance_preference} />
          <Row label="Intake method" value={spec.source_context?.intake_method ?? "—"} />
          <Row label="Confirmed" value={spec.confirmed ? `Yes · ${spec.confirmed_at ?? ""}` : "No"} />
        </Card>
        <Card title="Requested services">
          <Row label="Packing" value={spec.services?.packing ? "Yes" : "No"} />
          <Row label="Disassembly" value={spec.services?.disassembly ? "Yes" : "No"} />
          <Row
            label="Storage"
            value={
              spec.services?.storage
                ? `Yes${spec.services.storage_days ? ` · ${spec.services.storage_days} days` : ""}`
                : "No"
            }
          />
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <LocationCard title="Origin" loc={spec.origin} />
        <LocationCard title="Destination" loc={spec.destination} />
      </div>

      <Card title={`Inventory (${spec.inventory.length} line items)`}>
        <ul className="divide-y divide-border">
          {spec.inventory.map((it) => (
            <li key={it.item_id} className="flex flex-wrap items-center gap-3 py-3">
              <span className="min-w-[3ch] rounded bg-muted px-2 py-0.5 text-center text-xs font-medium">
                ×{it.quantity}
              </span>
              <span className="font-medium text-ink">{it.name}</span>
              <span className="text-xs text-muted-foreground">{it.room}</span>
              {it.oversized && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
                  Oversized
                </span>
              )}
              {it.fragile && (
                <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-destructive">
                  Fragile
                </span>
              )}
              {it.notes && <span className="ml-auto text-xs text-muted-foreground">{it.notes}</span>}
            </li>
          ))}
        </ul>
      </Card>

      {spec.oversized_or_fragile_items && spec.oversized_or_fragile_items.length > 0 && (
        <Card title="Flagged items summary">
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {spec.oversized_or_fragile_items.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </Card>
      )}
    </div>
  );
}

function LocationCard({ title, loc }: { title: string; loc: LocationSpec }) {
  return (
    <Card title={title}>
      <Row label="Address" value={loc.address_summary} />
      <Row label="Dwelling" value={loc.dwelling_type} />
      <Row label="Floors" value={String(loc.floors)} />
      <Row label="Stairs" value={String(loc.stairs)} />
      <Row label="Elevator" value={loc.elevator_access ? "Yes" : "No"} />
      <Row label="Parking distance" value={`${loc.parking_distance_feet} ft`} />
      {loc.access_notes && <Row label="Access notes" value={loc.access_notes} />}
    </Card>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-card p-5">
      <h2 className="font-display text-lg text-ink">{title}</h2>
      <div className="mt-3 space-y-1 text-sm">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-1">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-ink">{value}</span>
    </div>
  );
}

export function StatePill({ state }: { state: JobRecord["state"] }) {
  const colors: Record<string, string> = {
    draft: "bg-muted text-muted-foreground",
    intake_complete: "bg-mint/40 text-mint-foreground",
    confirmed: "bg-primary/10 text-primary",
    calling: "bg-accent text-accent-foreground",
    quotes_ready: "bg-mint/60 text-mint-foreground",
    negotiating: "bg-accent text-accent-foreground",
    completed: "bg-primary text-primary-foreground",
    failed: "bg-destructive/10 text-destructive",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider ${colors[state] ?? "bg-muted"}`}
    >
      {state.replace(/_/g, " ")}
    </span>
  );
}

