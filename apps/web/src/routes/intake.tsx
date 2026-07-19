import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { VoiceIntakePanel } from "@/components/veramove/VoiceIntakePanel";
import { DocumentUploadPanel } from "@/components/veramove/DocumentUploadPanel";
import { Button } from "@/components/ui/button";
import { FlaskConical, ArrowRight } from "lucide-react";
import { DEMO_JOB_ID } from "@/lib/api";
import { setRuntimeMode, useRuntimeMode } from "@/api/client";

export const Route = createFileRoute("/intake")({
  head: () => ({
    meta: [
      { title: "Intake · VeraMove" },
      {
        name: "description",
        content:
          "Start with a voice interview, paste an existing quote, or load the demo. Every path produces the same structured move specification.",
      },
    ],
  }),
  component: IntakePage,
});

function IntakePage() {
  const navigate = useNavigate();
  const mode = useRuntimeMode();
  const goConfirm = (jobId: string) => navigate({ to: "/confirm/$jobId", params: { jobId } });

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Tell us about your move</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Pick whichever is easier — a short voice interview, paste an existing quote or inventory,
          or load the demo move. Every path produces the same structured spec, which you'll review
          before any calls are made.
        </p>
      </header>

      {/* Third entry: Demo. Kept as a compact banner so the two working
          intake panels stay the primary focus of the page. */}
      <aside
        aria-label="Load demo move"
        className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-border bg-surface-muted p-4"
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-caution-soft text-caution-foreground">
            <FlaskConical className="h-4 w-4" aria-hidden />
          </div>
          <div>
            <h2 className="text-sm font-semibold">Skip intake — load the demo move</h2>
            <p className="text-sm text-muted-foreground">
              Explore the full flow with the seeded Rock Hill → Charlotte scenario. Synthetic data
              and role-play vendors — clearly labeled.
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          className="gap-1.5"
          onClick={() => {
            const target = `/confirm/${DEMO_JOB_ID}`;
            if (mode === "demo") {
              navigate({ to: "/confirm/$jobId", params: { jobId: DEMO_JOB_ID } });
            } else {
              // Explicit switch — never silent.
              setRuntimeMode("demo", { redirectTo: target });
            }
          }}
        >
          Load demo move <ArrowRight className="h-4 w-4" />
        </Button>
      </aside>

      <div className="grid gap-5 lg:grid-cols-2">
        <VoiceIntakePanel onComplete={goConfirm} />
        <DocumentUploadPanel onComplete={goConfirm} />
      </div>

      <p className="text-xs text-muted-foreground">
        In Live mode, document text is parsed server-side via
        <code className="mx-1 rounded bg-muted px-1 py-0.5 text-[11px]">
          POST /api/intake/document
        </code>
        . Live voice uses a short-lived server-issued credential and returns the same canonical
        JobSpec as document intake. Binary file upload remains a Demo Mode preview.
      </p>
    </div>
  );
}
