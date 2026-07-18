import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type JobRecord } from "../api/client";
import { ErrorState, LoadingState } from "../components/AsyncState";

export function ConfirmPage() {
  const { jobId = "" } = useParams();
  const [record, setRecord] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    api.getJob(jobId).then(setRecord).catch((reason: Error) => setError(reason.message));
  }, [jobId]);

  async function confirm() {
    setWorking(true);
    setError(null);
    try {
      setRecord(await api.confirmJob(jobId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to confirm job");
    } finally {
      setWorking(false);
    }
  }

  if (error) return <ErrorState message={error} />;
  if (!record) return <LoadingState label="Loading JobSpec…" />;

  const spec = record.job_spec;
  const services = spec.services;
  const activeServices = [
    services.packing ? "Packing" : null,
    services.disassembly ? "Disassembly" : null,
    services.storage ? `Storage${services.storage_days ? ` (${services.storage_days} days)` : ""}` : null,
  ].filter((label): label is string => Boolean(label));

  return (
    <section className="card space-y-6">
      <div>
        <p className="text-sm font-bold uppercase tracking-widest text-teal">Step 2</p>
        <h1 className="text-3xl font-bold">Confirm and lock the JobSpec</h1>
        <p className="mt-2 text-sm text-ink/70">
          This is the exact specification every vendor call will use. Review it fully before locking —
          once confirmed, this version cannot change.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="font-semibold">Move date</dt>
          <dd>
            {spec.move_date}
            {spec.date_flexible ? <span className="ml-2 text-sm text-ink/60">(flexible)</span> : null}
          </dd>
        </div>
        <div>
          <dt className="font-semibold">Bedrooms</dt>
          <dd>{spec.bedroom_count}</dd>
        </div>
        <div>
          <dt className="font-semibold">Intake method</dt>
          <dd className="capitalize">{spec.source_context.intake_method ?? "unspecified"}</dd>
        </div>
        <div>
          <dt className="font-semibold">Insurance preference</dt>
          <dd>{spec.insurance_preference}</dd>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg bg-sand p-4">
          <h2 className="font-semibold text-teal">Origin</h2>
          <p className="mt-1">{spec.origin.address_summary}</p>
          <ul className="mt-2 space-y-1 text-sm text-ink/70">
            <li>Dwelling: {spec.origin.dwelling_type}, {spec.origin.floors} floor(s)</li>
            <li>Stairs: {spec.origin.stairs}</li>
            <li>Elevator access: {spec.origin.elevator_access ? "Yes" : "No"}</li>
            <li>Parking distance: {spec.origin.parking_distance_feet} ft</li>
            <li>{spec.origin.access_notes}</li>
          </ul>
        </div>
        <div className="rounded-lg bg-sand p-4">
          <h2 className="font-semibold text-teal">Destination</h2>
          <p className="mt-1">{spec.destination.address_summary}</p>
          <ul className="mt-2 space-y-1 text-sm text-ink/70">
            <li>Dwelling: {spec.destination.dwelling_type}, {spec.destination.floors} floor(s)</li>
            <li>Stairs: {spec.destination.stairs}</li>
            <li>Elevator access: {spec.destination.elevator_access ? "Yes" : "No"}</li>
            <li>Parking distance: {spec.destination.parking_distance_feet} ft</li>
            <li>{spec.destination.access_notes}</li>
          </ul>
        </div>
      </div>

      <div>
        <h2 className="font-semibold text-teal">Inventory</h2>
        <ul className="mt-2 space-y-2">
          {spec.inventory.map((item) => (
            <li className="rounded-lg border border-teal/10 p-3" key={item.item_id}>
              <p className="font-medium">
                {item.quantity}x {item.name}
                {item.oversized ? <span className="ml-2 text-xs font-semibold text-amber-600">OVERSIZED</span> : null}
                {item.fragile ? <span className="ml-2 text-xs font-semibold text-red-600">FRAGILE</span> : null}
              </p>
              <p className="text-sm text-ink/70">
                {item.room}
                {item.notes ? ` — ${item.notes}` : ""}
              </p>
            </li>
          ))}
        </ul>
        {spec.oversized_or_fragile_items.length ? (
          <p className="mt-2 text-sm text-ink/70">
            Flagged for special handling: {spec.oversized_or_fragile_items.join(", ")}
          </p>
        ) : null}
      </div>

      <div>
        <h2 className="font-semibold text-teal">Requested services</h2>
        <p className="mt-1 text-sm text-ink/70">
          {activeServices.length ? activeServices.join(", ") : "None requested"}
        </p>
      </div>

      {record.job_spec.confirmed ? (
        <Link className="link-button" to={`/calls/${jobId}`}>
          Start vendor calls
        </Link>
      ) : (
        <button className="button" disabled={working} onClick={confirm} type="button">
          {working ? "Locking…" : "Confirm JobSpec"}
        </button>
      )}
    </section>
  );
}
