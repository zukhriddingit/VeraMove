import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

export const Route = createFileRoute("/")({
  component: HomePage,
});

function HomePage() {
  const navigate = useNavigate();
  const [jumpId, setJumpId] = useState("");
  const trimmed = jumpId.trim();

  return (
    <div className="space-y-16">
      <section className="grid gap-10 pt-6 md:grid-cols-[1.3fr_1fr] md:items-center">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-mint/40 px-3 py-1 text-xs font-medium uppercase tracking-wider text-primary">
            AI moving-services negotiator
          </span>
          <h1 className="mt-5 font-display text-5xl leading-tight text-ink md:text-6xl">
            One locked spec.<br />
            Three vendor calls.<br />
            <span className="text-primary">Evidence-backed negotiation.</span>
          </h1>
          <p className="mt-5 max-w-xl text-lg text-muted-foreground">
            VeraMove takes your move details, freezes them into a single spec, then places
            synthetic calls to vendors — capturing quotes, hidden fees, and red flags —
            before recommending the best deal with recording-level evidence.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/intake"
              className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
            >
              Start a new intake →
            </Link>
            <a
              href="#jump"
              className="inline-flex items-center justify-center rounded-md border border-border bg-card px-5 py-3 text-sm font-medium hover:bg-accent"
            >
              Jump to an existing job
            </a>
          </div>
        </div>
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            How the demo flows
          </div>
          <ol className="mt-4 space-y-4 text-sm">
            {[
              ["1", "Intake", "Voice or document — produces one JobSpec"],
              ["2", "Confirm", "Review + lock the spec (version 1)"],
              ["3", "Calls", "3 synthetic vendor calls → quotes"],
              ["4", "Negotiate", "Verified spec used as leverage"],
              ["5", "Report", "Ranked recommendation w/ evidence"],
            ].map(([n, title, desc]) => (
              <li key={n} className="flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {n}
                </span>
                <div>
                  <div className="font-medium text-ink">{title}</div>
                  <div className="text-muted-foreground">{desc}</div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="jump" className="rounded-2xl border border-border bg-sand p-8">
        <h2 className="font-display text-2xl text-ink">Jump into an existing demo job</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Paste a <code className="rounded bg-background px-1 py-0.5 text-xs">job_id</code> to jump to any step.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <input
            className="w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            placeholder="job_abc123…"
            value={jumpId}
            onChange={(e) => setJumpId(e.target.value)}
          />
          {[
            { label: "Confirm", to: "/confirm/$jobId" as const },
            { label: "Calls", to: "/calls/$jobId" as const },
            { label: "Report", to: "/report/$jobId" as const },
          ].map((b) => (
            <button
              key={b.label}
              disabled={!trimmed}
              onClick={() => navigate({ to: b.to, params: { jobId: trimmed } })}
              className="rounded-md border border-border bg-card px-4 py-2 text-sm font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              Go to {b.label}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
