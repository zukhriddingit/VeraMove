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
          {quotes.slice(0, 3).map((quote) => {
            const hiddenFees = quote.fee_line_items.filter((fee) => !fee.disclosed_upfront);
            const disclosedFees = quote.fee_line_items.filter((fee) => fee.disclosed_upfront);
            const wasNegotiated = quote.original_total !== quote.negotiated_total;
            const redFlags = quote.red_flags ?? [];

            return (
              <article className="card space-y-3" key={quote.quote_id}>
                <div>
                  <h2 className="font-bold">{quote.vendor.name}</h2>
                  <p className="text-sm text-ink/60">{quote.verification_status}</p>
                </div>

                <div>
                  {wasNegotiated ? (
                    <p>
                      <span className="text-sm text-ink/50 line-through">
                        {quote.currency} {quote.original_total}
                      </span>{" "}
                      <span className="font-bold text-teal">{quote.currency} {quote.negotiated_total}</span>
                    </p>
                  ) : (
                    <p className="font-bold">{quote.currency} {quote.negotiated_total}</p>
                  )}
                  <p className="text-sm text-ink/60">Deposit: {quote.currency} {quote.deposit}</p>
                  <p className="text-sm text-ink/60">Binding: {quote.binding_type}</p>
                </div>

                {redFlags.length ? (
                  <div className="rounded-lg bg-red-50 p-3">
                    <p className="text-sm font-semibold text-red-700">Red flags</p>
                    <ul className="mt-1 space-y-1 text-sm text-red-700">
                      {redFlags.map((flag) => (
                        <li key={flag}>{flag}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {hiddenFees.length ? (
                  <div className="rounded-lg bg-amber-50 p-3">
                    <p className="text-sm font-semibold text-amber-700">
                      Hidden fees found ({hiddenFees.length})
                    </p>
                    <ul className="mt-1 space-y-1 text-sm text-amber-700">
                      {hiddenFees.map((fee) => (
                        <li key={fee.description}>
                          {fee.description} — {quote.currency} {fee.amount}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="text-sm text-ink/50">No hidden fees found — every fee was disclosed upfront.</p>
                )}

                {disclosedFees.length ? (
                  <details className="text-sm text-ink/60">
                    <summary className="cursor-pointer font-semibold text-ink/70">
                      Disclosed fees ({disclosedFees.length})
                    </summary>
                    <ul className="mt-1 space-y-1">
                      {disclosedFees.map((fee) => (
                        <li key={fee.description}>
                          {fee.description} — {quote.currency} {fee.amount}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}

                {quote.concessions?.length ? (
                  <p className="text-sm text-ink/60">Concessions: {quote.concessions.join(", ")}</p>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
