import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type JobRecord } from "../api/client";
import { ErrorState, LoadingState } from "../components/AsyncState";

export function CallsPage() {
  const { jobId = "" } = useParams();
  const [record, setRecord] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    api.getJob(jobId).then(setRecord).catch((reason: Error) => setError(reason.message));
  }, [jobId]);

  async function run(action: "calls" | "negotiate") {
    setWorking(true);
    setError(null);
    try {
      setRecord(action === "calls" ? await api.startCalls(jobId) : await api.negotiate(jobId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Workflow action failed");
    } finally {
      setWorking(false);
    }
  }

  if (error) return <ErrorState message={error} />;
  if (!record) return <LoadingState label="Loading call workspace…" />;
  const quotes = record.quotes ?? [];

  return (
    <section className="space-y-5">
      <div className="card space-y-4">
        <p className="text-sm font-bold uppercase tracking-widest text-teal">Steps 3–6</p>
        <h1 className="text-3xl font-bold">Call three vendors and negotiate</h1>
        <p>Current state: <strong>{record.state}</strong></p>
        {record.state === "confirmed" ? (
          <button className="button" disabled={working} onClick={() => run("calls")} type="button">
            {working ? "Calling…" : "Create three mock calls"}
          </button>
        ) : null}
        {record.state === "quotes_ready" ? (
          <button className="button" disabled={working} onClick={() => run("negotiate")} type="button">
            {working ? "Negotiating…" : "Negotiate with verified quote"}
          </button>
        ) : null}
        {record.state === "completed" ? (
          <Link className="link-button" to={`/report/${jobId}`}>View final report</Link>
        ) : null}
      </div>
      {quotes.length ? (
        <div className="grid gap-4 md:grid-cols-3">
          {quotes.slice(0, 3).map((quote) => (
            <article className="card" key={quote.quote_id}>
              <h2 className="font-bold">{quote.vendor.name}</h2>
              <p>{quote.currency} {quote.negotiated_total}</p>
              <p className="text-sm">{quote.verification_status}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
