import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { api, formatCurrency } from "@/lib/api";
import { ErrorBox, LoadingCard, Stepper } from "@/components/flow";

export const Route = createFileRoute("/report/$jobId")({
  head: () => ({
    meta: [
      { title: "Recommendation report — VeraMove" },
      { name: "description", content: "Evidence-backed vendor ranking and final recommendation." },
    ],
  }),
  component: ReportPage,
});

function ReportPage() {
  const { jobId } = useParams({ from: "/report/$jobId" });
  const { data, isLoading, error } = useQuery({
    queryKey: ["report", jobId],
    queryFn: () => api.getReport(jobId),
  });

  if (isLoading) return <div className="py-16 text-center text-muted-foreground">Loading report…</div>;
  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!data) return null;

  return (
    <div className="space-y-10">
      <header>
        <div className="text-xs uppercase tracking-wider text-muted-foreground">Step 5 · Recommendation</div>
        <h1 className="mt-1 font-display text-4xl text-ink">Final report</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Job <code className="rounded bg-muted px-1 py-0.5 text-xs">{jobId}</code> · report{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">{data.recommendation_id}</code>
        </p>
      </header>

      <section className="rounded-2xl border border-primary/20 bg-mint/30 p-6">
        <div className="text-xs font-semibold uppercase tracking-wider text-primary">Summary</div>
        <p className="mt-2 font-display text-xl text-ink">{data.summary}</p>
      </section>

      <section className="space-y-4">
        <h2 className="font-display text-2xl text-ink">Vendor rankings</h2>
        {data.rankings
          .slice()
          .sort((a, b) => a.rank - b.rank)
          .map((r) => {
            const winner = r.vendor.vendor_id === data.winning_vendor_id;
            return (
              <article
                key={r.quote_id}
                className={`rounded-2xl border p-6 ${winner ? "border-primary bg-card shadow-md" : "border-border bg-card"}`}
              >
                <header className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span
                      className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold ${
                        winner ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                      }`}
                    >
                      #{r.rank}
                    </span>
                    <div>
                      <h3 className="font-display text-xl text-ink">
                        {r.vendor.name}
                        {winner && (
                          <span className="ml-2 rounded-full bg-mint px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-mint-foreground">
                            Winner
                          </span>
                        )}
                      </h3>
                      <div className="text-xs text-muted-foreground">
                        Quote <code>{r.quote_id}</code>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-display text-2xl text-ink">{formatCurrency(r.total)}</div>
                    <div className="text-xs text-muted-foreground">
                      {r.evidence_ids.length} evidence ref{r.evidence_ids.length === 1 ? "" : "s"}
                    </div>
                  </div>
                </header>

                {r.rationale.length > 0 && (
                  <div className="mt-4">
                    <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Rationale
                    </div>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
                      {r.rationale.map((line, i) => <li key={i}>{line}</li>)}
                    </ul>
                  </div>
                )}

                {r.red_flags && r.red_flags.length > 0 && (
                  <div className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 p-3">
                    <div className="text-xs font-semibold uppercase tracking-wider text-destructive">
                      🚩 Red flags
                    </div>
                    <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-destructive">
                      {r.red_flags.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                )}
              </article>
            );
          })}
      </section>

      <section>
        <h2 className="font-display text-2xl text-ink">Transcript evidence</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Every ranking claim traces back to a recorded vendor call.
        </p>
        {data.transcript_evidence.length === 0 ? (
          <div className="mt-3 text-sm text-muted-foreground">No transcript evidence attached.</div>
        ) : (
          <ul className="mt-4 space-y-3">
            {data.transcript_evidence.map((e) => (
              <li key={e.evidence_id} className="rounded-xl border border-border bg-card p-4">
                <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {e.evidence_id}
                </div>
                <p className="mt-1 text-sm text-ink">"{e.claim}"</p>
                <a
                  href={e.recording_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block text-xs font-medium text-primary hover:underline"
                >
                  🎧 Listen to source recording
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div>
        <Link to="/" className="text-sm text-primary hover:underline">← Back to home</Link>
      </div>
    </div>
  );
}
