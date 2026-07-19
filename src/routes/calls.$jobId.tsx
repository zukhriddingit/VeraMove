import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, formatCurrency, type QuoteV1, type CallRecord } from "@/lib/api";
import { ErrorBox, LoadingCard, Stepper } from "@/components/flow";
import { StatePill } from "./confirm.$jobId";

export const Route = createFileRoute("/calls/$jobId")({
  head: () => ({
    meta: [
      { title: "Vendor calls — VeraMove" },
      { name: "description", content: "Synthetic vendor calls, quotes, and negotiation." },
    ],
  }),
  component: CallsPage,
});

type ChecklistItem = {
  label: string;
  description: string;
  satisfied: boolean;
  caption: string;
};

function ConversationChecklist({ calls }: { calls: CallRecord[] }) {
  const hasCalls = calls.length > 0;
  const callbackSurvived = calls.some((c) => c.outcome.type === "callback_commitment");
  const allClosed =
    hasCalls &&
    calls.every((c) =>
      ["itemized_quote", "callback_commitment", "documented_decline"].includes(c.outcome.type)
    );

  const items: ChecklistItem[] = [
    {
      label: "AI disclosure",
      description:
        "Every call opens with a clear AI disclosure and answers 'are you a robot?' honestly.",
      satisfied: hasCalls,
      caption: hasCalls ? "Built into every synthetic call" : "Pending first call",
    },
    {
      label: "Friction survival",
      description:
        "At least one call survives real friction (hold music, a rushed dispatcher) and secures a structured callback instead of a dead end.",
      satisfied: callbackSurvived,
      caption: callbackSurvived ? "Observed in this batch" : "Not observed in this batch",
    },
    {
      label: "Honesty line",
      description:
        "The agent may use a real verified competing quote as leverage. It must never invent inventory, fabricate a competitor's number, or misrepresent the job spec.",
      satisfied: hasCalls,
      caption: hasCalls ? "Built-in guardrail, not vendor-dependent" : "Pending first call",
    },
    {
      label: "Structured close",
      description:
        "No call ends on a vague answer — every call closes as an itemized quote, a callback commitment, or a documented decline.",
      satisfied: allClosed,
      caption: allClosed
        ? "All calls closed cleanly"
        : hasCalls
          ? "Some calls need follow-up"
          : "Pending first call",
    },
  ];

  return (
    <section className="rounded-2xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
          4
        </span>
        <div>
          <h2 className="font-display text-lg text-ink">Conversation-design checklist</h2>
          <p className="text-xs text-muted-foreground">
            What we expect from every synthetic call batch
          </p>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {items.map((item) => (
          <div
            key={item.label}
            className={`rounded-xl border border-border p-4 ${
              item.satisfied ? "bg-mint/15" : "bg-sand/50"
            }`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${
                  item.satisfied ? "bg-mint" : "bg-muted-foreground/30"
                }`}
              />
              <div>
                <div
                  className={`text-sm font-semibold ${
                    item.satisfied ? "text-mint-foreground" : "text-foreground"
                  }`}
                >
                  {item.label}
                </div>
                <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {item.description}
                </div>
                <div
                  className={`mt-2 text-[10px] font-medium uppercase tracking-wider ${
                    item.satisfied ? "text-mint-foreground/80" : "text-muted-foreground/70"
                  }`}
                >
                  {item.caption}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function CallsPage() {

  const { jobId } = useParams({ from: "/calls/$jobId" });
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId),
  });

  const callsMut = useMutation({
    mutationFn: () => api.createCalls(jobId),
    onSuccess: (j) => qc.setQueryData(["job", jobId], j),
  });
  const negMut = useMutation({
    mutationFn: () => api.negotiate(jobId),
    onSuccess: (j) => qc.setQueryData(["job", jobId], j),
  });

  if (isLoading)
    return (
      <div className="space-y-6">
        <Stepper current="calls" jobId={jobId} />
        <LoadingCard label="Loading job…" />
      </div>
    );
  if (error)
    return (
      <div className="space-y-6">
        <Stepper current="calls" jobId={jobId} />
        <ErrorBox message={(error as Error).message} />
      </div>
    );
  if (!data) return null;


  const { state, quotes, calls } = data;

  return (
    <div className="space-y-8">
      <Stepper current="calls" jobId={jobId} />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground">Step 3 · Vendor calls</div>
          <h1 className="mt-1 font-display text-4xl text-ink">Quotes & negotiation</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Job <code className="rounded bg-muted px-1 py-0.5 text-xs">{jobId}</code> · state <StatePill state={state} />
          </p>
        </div>
        <div className="flex gap-3">
          {state === "confirmed" && (
            <button
              onClick={() => callsMut.mutate()}
              disabled={callsMut.isPending}
              className="rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
            >
              {callsMut.isPending ? "Placing calls…" : "Place 3 vendor calls"}
            </button>
          )}
          {state === "quotes_ready" && (
            <button
              onClick={() => negMut.mutate()}
              disabled={negMut.isPending}
              className="rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:opacity-50"
            >
              {negMut.isPending ? "Negotiating…" : "Negotiate with verified quote"}
            </button>
          )}
          {state === "completed" && (
            <Link
              to="/report/$jobId"
              params={{ jobId }}
              className="rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
            >
              View final report →
            </Link>
          )}
        </div>
      </header>

      {callsMut.error && <ErrorBox message={(callsMut.error as Error).message} />}
      {negMut.error && <ErrorBox message={(negMut.error as Error).message} />}

      {state !== "confirmed" && <ConversationChecklist calls={calls} />}

      {quotes.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-sand p-10 text-center text-muted-foreground">
          {state === "confirmed"
            ? "No quotes yet. Kick off the 3 vendor calls to generate synthetic quotes."
            : "Waiting on backend to produce quotes."}
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          {quotes.map((q) => <QuoteCard key={q.quote_id} q={q} />)}
        </div>
      )}

    </div>
  );
}

function verificationStyle(status: QuoteV1["verification_status"]) {
  switch (status) {
    case "verified":
      return "bg-mint/60 text-mint-foreground";
    case "partially_verified":
      return "bg-accent text-accent-foreground";
    default:
      return "bg-destructive/10 text-destructive";
  }
}

function QuoteCard({ q }: { q: QuoteV1 }) {
  const [feesOpen, setFeesOpen] = useState(false);
  const negotiated = q.negotiated_total !== q.original_total;
  const hiddenFees = q.fee_line_items.filter((f) => !f.disclosed_upfront);

  return (
    <article className="flex flex-col rounded-2xl border border-border bg-card p-5 shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-xl text-ink">{q.vendor.name}</h3>
          <div className="mt-1 text-xs text-muted-foreground">
            {q.availability} · {q.binding_type.replace("_", "-")}
          </div>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${verificationStyle(q.verification_status)}`}
        >
          {q.verification_status.replace(/_/g, " ")}
        </span>
      </header>

      <div className="mt-4">
        <div className="flex items-baseline gap-3">
          {negotiated && (
            <span className="text-sm text-muted-foreground line-through">
              {formatCurrency(q.original_total, q.currency)}
            </span>
          )}
          <span className="font-display text-3xl text-ink">
            {formatCurrency(q.negotiated_total, q.currency)}
          </span>
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          Deposit {formatCurrency(q.deposit, q.currency)}
        </div>
      </div>

      {q.red_flags && q.red_flags.length > 0 && (
        <div className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 p-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-destructive">
            🚩 Red flags
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-destructive">
            {q.red_flags.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      <div
        className={`mt-4 rounded-lg p-3 ${
          hiddenFees.length > 0 ? "border border-destructive/30 bg-destructive/5" : "border border-mint/60 bg-mint/20"
        }`}
      >
        <div className={`text-xs font-semibold uppercase tracking-wider ${hiddenFees.length ? "text-destructive" : "text-mint-foreground"}`}>
          {hiddenFees.length > 0 ? "⚠️ Hidden fees" : "✓ No hidden fees found"}
        </div>
        {hiddenFees.length > 0 && (
          <ul className="mt-1 space-y-1 text-xs">
            {hiddenFees.map((f, i) => (
              <li key={i} className="flex justify-between">
                <span className="text-destructive">{f.description}</span>
                <span className="font-medium text-destructive">{formatCurrency(f.amount, q.currency)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-4">
        <button
          onClick={() => setFeesOpen((v) => !v)}
          className="flex w-full items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-xs font-medium hover:bg-accent"
        >
          <span>Disclosed fees ({q.fee_line_items.length})</span>
          <span>{feesOpen ? "−" : "+"}</span>
        </button>
        {feesOpen && (
          <ul className="mt-2 space-y-1 text-xs">
            {q.fee_line_items.map((f, i) => (
              <li key={i} className="flex justify-between gap-2">
                <span className="text-muted-foreground">
                  {f.description}
                  <span className="ml-1 text-[10px] uppercase tracking-wider text-muted-foreground/70">
                    {f.category}
                  </span>
                  {!f.disclosed_upfront && (
                    <span className="ml-1 text-[10px] font-semibold text-destructive">hidden</span>
                  )}
                </span>
                <span className="font-medium">{formatCurrency(f.amount, q.currency)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {q.concessions && q.concessions.length > 0 && (
        <div className="mt-4 rounded-lg bg-mint/20 p-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-mint-foreground">
            🎁 Concessions won
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-mint-foreground">
            {q.concessions.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      )}

      {q.recording_url && (
        <a
          href={q.recording_url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 text-xs font-medium text-primary hover:underline"
        >
          🎧 Listen to call recording
        </a>
      )}
    </article>
  );
}
