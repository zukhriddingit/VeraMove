import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { api } from "@/lib/api";
import { buildDocumentIntakeSpec, buildVoiceIntakeSpec } from "@/lib/mock-specs";
import { ErrorBox, Stepper } from "@/components/flow";

export const Route = createFileRoute("/intake")({
  head: () => ({
    meta: [
      { title: "Intake — VeraMove" },
      { name: "description", content: "Simulated voice or document intake for a demo move." },
    ],
  }),
  component: IntakePage,
});

type Mode = "voice" | "document";

function IntakePage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("voice");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = mode === "voice" || (mode === "document" && file !== null);

  async function handleSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      const spec = mode === "voice" ? buildVoiceIntakeSpec() : buildDocumentIntakeSpec();
      const job = await api.createJob(spec);
      navigate({ to: "/confirm/$jobId", params: { jobId: job.job_spec.job_id } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <Stepper current="intake" />
      <div>
        <h1 className="font-display text-4xl text-ink">Start a demo intake</h1>
        <p className="mt-2 text-muted-foreground">
          Both modes produce a fully synthetic <code className="rounded bg-muted px-1 py-0.5 text-xs">JobSpecV1</code>.
          Nothing is transcribed or parsed — this is a mock flow to exercise the backend.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-card p-1">
        {(["voice", "document"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`rounded-lg px-4 py-3 text-sm font-medium capitalize transition ${
              mode === m
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-accent"
            }`}
          >
            {m === "voice" ? "🎙️ Voice intake" : "📄 Document upload"}
          </button>
        ))}
      </div>

      {mode === "voice" ? (
        <div className="rounded-xl border border-border bg-card p-6">
          <h2 className="font-display text-xl text-ink">Voice intake (simulated)</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            In a real deployment, Vera would call the customer, ask about their move, and build
            the spec live. For the demo, tapping <em>Submit</em> generates a synthetic 2-bedroom
            apartment→condo move in the East Bay and posts it to the backend.
          </p>
          <div className="mt-4 rounded-lg bg-mint/30 p-4 text-sm text-mint-foreground">
            <div className="font-medium">Demo spec preview</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
              <li>Apartment (Oakland) → Condo (Alameda), 2 bedrooms</li>
              <li>Move in ~3 weeks, date flexible</li>
              <li>Packing + disassembly requested</li>
              <li>Oversized dining table, fragile 55" TV</li>
            </ul>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card p-6">
          <h2 className="font-display text-xl text-ink">Document upload (simulated parse)</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Upload any file to simulate a parsed inventory PDF. The backend receives a
            synthetic 3-bedroom house→house move with a sectional sofa and upright piano.
          </p>
          <label className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-sand py-8 text-center hover:bg-accent">
            <input
              type="file"
              className="sr-only"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <span className="text-sm font-medium text-ink">
              {file ? `📎 ${file.name}` : "Click to select a file (any type)"}
            </span>
            <span className="mt-1 text-xs text-muted-foreground">
              File contents are ignored — this is a simulated parse.
            </span>
          </label>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          Synthetic data only. No real customer PII is sent.
        </div>
        <button
          disabled={!canSubmit || submitting}
          onClick={handleSubmit}
          className="rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Creating job…" : "Submit intake →"}
        </button>
      </div>
    </div>
  );
}
