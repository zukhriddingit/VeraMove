import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowRight, PhoneCall, ShieldCheck, Sparkles, Scale, ClipboardList, Mic, FileText, FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DEMO_JOB_ID } from "@/lib/api";
import { setRuntimeMode, useRuntimeMode } from "@/api/client";
import { HealthIndicator } from "@/components/veramove/HealthIndicator";
import { RuntimeModeBadge } from "@/components/veramove/RuntimeModeBadge";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "VeraMove — Get three moving quotes and negotiate the best deal." },
      {
        name: "description",
        content:
          "VeraMove gets three comparable moving quotes, detects hidden fees, negotiates a better deal, and returns a ranked recommendation backed by call evidence.",
      },
      { property: "og:title", content: "VeraMove — Get three moving quotes and negotiate the best deal." },
      {
        property: "og:description",
        content:
          "VeraMove gets three comparable moving quotes, detects hidden fees, negotiates a better deal, and returns a ranked recommendation backed by call evidence.",
      },
    ],
  }),
  component: Landing,
});

function Landing() {
  const navigate = useNavigate();
  const isDemoMode = useRuntimeMode() === "demo";

  return (
    <div className="flex flex-col gap-16">
      {/* Hero */}
      <section className="grid gap-10 pt-4 md:grid-cols-[1.15fr_1fr] md:items-center md:pt-8">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5" />
            VeraMove operates standalone today
          </span>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-foreground md:text-[44px] md:leading-[1.1]">
            Get three moving quotes and
            <br />
            <span className="text-verified">negotiate the best deal.</span>
          </h1>
          <p className="mt-5 max-w-xl text-base text-muted-foreground md:text-lg">
            One confirmed move specification. Three comparable quotes. Hidden
            fees surfaced, competing leverage applied, and a ranked
            recommendation with transcript evidence.
          </p>

          {/* Runtime + health surface — users always know what they're seeing. */}
          <div className="mt-5 flex flex-wrap items-center gap-2">
            <RuntimeModeBadge />
            <HealthIndicator
              onUseDemo={() =>
                setRuntimeMode("demo", { redirectTo: `/confirm/${DEMO_JOB_ID}` })
              }
            />
          </div>

          {isDemoMode && (
            <p className="mt-3 flex items-start gap-1.5 text-xs text-caution-foreground">
              <FlaskConical className="mt-0.5 h-3.5 w-3.5" aria-hidden />
              Demo mode uses synthetic vendors and role-played calls — nothing
              is dialed. Switch to Live to use the connected backend.
            </p>
          )}
        </div>

        {/* Hero card preview */}
        <div className="relative">
          <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm">
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Recommendation preview
              <span className="inline-flex items-center gap-1 rounded-full bg-verified-soft px-2 py-0.5 text-verified">
                <ShieldCheck className="h-3 w-3" />
                Evidence-backed
              </span>
            </div>
            <div className="mt-4">
              <div className="text-lg font-semibold">PremierMove</div>
              <div className="text-sm text-muted-foreground">
                Binding · packing materials included
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-2xl font-semibold tabular-nums">$1,900</span>
                <span className="text-xs text-muted-foreground line-through tabular-nums">
                  $2,200
                </span>
                <span className="rounded-full bg-verified px-2 py-0.5 text-xs font-medium text-verified-foreground">
                  $300 saved
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Three entry points — Voice, Document, Demo */}
      <section aria-label="Start your move">
        <h2 className="text-xl font-semibold tracking-tight">Start your move</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Three entry points. Voice and document both produce the same
          structured spec you'll review before any calls.
        </p>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <EntryCard
            icon={<Mic className="h-5 w-5" />}
            title="Start with voice"
            body="Two-minute conversation with an AI intake agent. Available in Demo today."
            cta="Voice interview"
            onClick={() => navigate({ to: "/intake" })}
          />
          <EntryCard
            icon={<FileText className="h-5 w-5" />}
            title="Start with document"
            body={isDemoMode
              ? "Upload a PDF/PNG/JPEG (Demo) or paste a moving estimate in Live."
              : "Paste a moving estimate, inventory, or move notes. We extract the details."}
            cta="Document intake"
            onClick={() => navigate({ to: "/intake" })}
          />
          <EntryCard
            icon={<FlaskConical className="h-5 w-5" />}
            title="Load a demo move"
            body="Skip intake and jump to the seeded Rock Hill → Charlotte move to explore the full flow."
            cta="Load demo"
            onClick={() => {
              const target = `/confirm/${DEMO_JOB_ID}`;
              if (isDemoMode) {
                navigate({ to: "/confirm/$jobId", params: { jobId: DEMO_JOB_ID } });
              } else {
                // Explicit switch — never silent. setRuntimeMode redirects.
                setRuntimeMode("demo", { redirectTo: target });
              }
            }}
            variant="outline"
          />
        </div>
      </section>

      {/* How it works */}
      <section>
        <h2 className="text-2xl font-semibold tracking-tight">How VeraMove works</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          One specification. Three calls. One evidence-backed recommendation.
        </p>
        <ol className="mt-6 grid gap-4 md:grid-cols-4">
          {[
            {
              icon: <ClipboardList className="h-4 w-4" />,
              title: "Intake",
              body: "Voice interview or upload an existing quote. Same structured spec either way.",
            },
            {
              icon: <ShieldCheck className="h-4 w-4" />,
              title: "Confirm",
              body: "You review and lock the move spec. It's reused on every vendor call.",
            },
            {
              icon: <PhoneCall className="h-4 w-4" />,
              title: "Calls",
              body: "Three vendors, four required conversation moves per call, all logged.",
            },
            {
              icon: <Scale className="h-4 w-4" />,
              title: "Recommendation",
              body: "Ranked result with tradeoffs and links to the evidence.",
            },
          ].map((s, i) => (
            <li
              key={s.title}
              className="rounded-2xl border border-border bg-surface p-5"
            >
              <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  {i + 1}
                </span>
                <span className="uppercase tracking-wide">{s.title}</span>
              </div>
              <div className="mt-3 flex h-8 w-8 items-center justify-center rounded-lg bg-muted text-foreground">
                {s.icon}
              </div>
              <p className="mt-3 text-sm text-foreground/90">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Trust strip */}
      <section className="rounded-2xl border border-border bg-surface p-6">
        <h2 className="text-lg font-semibold">Four requirements. Every call.</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          A call only counts when all four are met — with a transcript excerpt
          and a timestamp.
        </p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 md:grid-cols-4">
          {[
            ["AI disclosure", "The agent tells the vendor it's an AI, upfront."],
            ["Friction handled", "Objections and callbacks are pushed through, not accepted."],
            ["Verified leverage only", "We only cite quotes we've independently verified."],
            ["Structured ending", "Binding total, availability, and reference read back."],
          ].map(([t, d]) => (
            <div key={t} className="rounded-xl border border-border p-4">
              <div className="text-sm font-medium">{t}</div>
              <p className="mt-1 text-xs text-muted-foreground">{d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Future statement */}
      <section className="text-center text-sm text-muted-foreground">
        VeraMove operates independently today and is designed as a future
        move-in concierge for VeraAI.{" "}
        <Link
          to="/intake"
          className="font-medium text-foreground underline underline-offset-4"
        >
          Start a move
        </Link>
      </section>
    </div>
  );
}

function EntryCard({
  icon,
  title,
  body,
  cta,
  onClick,
  variant = "default",
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  cta: string;
  onClick: () => void;
  variant?: "default" | "outline";
}) {
  return (
    <div className="flex flex-col rounded-2xl border border-border bg-surface p-5">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
        {icon}
      </div>
      <div className="mt-4 text-base font-semibold">{title}</div>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
      <div className="mt-auto pt-4">
        <Button onClick={onClick} variant={variant} className="w-full gap-1.5">
          {cta}
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
