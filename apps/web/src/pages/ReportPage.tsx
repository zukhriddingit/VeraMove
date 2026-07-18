import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, type RecommendationV1 } from "../api/client";
import { ErrorState, LoadingState } from "../components/AsyncState";

export function ReportPage() {
  const { jobId = "" } = useParams();
  const [report, setReport] = useState<RecommendationV1 | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getReport(jobId).then(setReport).catch((reason: Error) => setError(reason.message));
  }, [jobId]);

  if (error) return <ErrorState message={error} />;
  if (!report) return <LoadingState label="Loading evidence-backed report…" />;

  return (
    <section className="space-y-5">
      <div className="card">
        <p className="text-sm font-bold uppercase tracking-widest text-teal">Step 7</p>
        <h1 className="mt-2 text-3xl font-bold">Final recommendation</h1>
        <p className="mt-4">{report.summary}</p>
      </div>
      <ol className="space-y-4">
        {report.rankings.map((ranking) => (
          <li className="card" key={ranking.quote_id}>
            <p className="text-sm font-semibold text-teal">Rank {ranking.rank}</p>
            <h2 className="text-xl font-bold">{ranking.vendor.name}</h2>
            <p>USD {ranking.total}</p>
            <ul className="mt-3 list-disc pl-5">
              {ranking.rationale.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
            <p className="mt-3 text-sm">Evidence references: {ranking.evidence_ids.length}</p>
          </li>
        ))}
      </ol>
      <div className="card">
        <h2 className="text-xl font-bold">Transcript and recording evidence</h2>
        <ul className="mt-3 space-y-3">
          {report.transcript_evidence.map((evidence) => (
            <li key={evidence.evidence_id}>
              <p>{evidence.claim}</p>
              <a className="text-sm font-semibold text-teal underline" href={evidence.recording_url}>
                Synthetic recording reference
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
