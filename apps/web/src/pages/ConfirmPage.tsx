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

  return (
    <section className="card space-y-5">
      <p className="text-sm font-bold uppercase tracking-widest text-teal">Step 2</p>
      <h1 className="text-3xl font-bold">Confirm and lock the JobSpec</h1>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div><dt className="font-semibold">Move date</dt><dd>{record.job_spec.move_date}</dd></div>
        <div><dt className="font-semibold">Bedrooms</dt><dd>{record.job_spec.bedroom_count}</dd></div>
        <div><dt className="font-semibold">Origin</dt><dd>{record.job_spec.origin.address_summary}</dd></div>
        <div><dt className="font-semibold">Destination</dt><dd>{record.job_spec.destination.address_summary}</dd></div>
      </dl>
      {record.job_spec.confirmed ? (
        <Link className="link-button" to={`/calls/${jobId}`}>Start vendor calls</Link>
      ) : (
        <button className="button" disabled={working} onClick={confirm} type="button">
          {working ? "Locking…" : "Confirm JobSpec"}
        </button>
      )}
    </section>
  );
}
