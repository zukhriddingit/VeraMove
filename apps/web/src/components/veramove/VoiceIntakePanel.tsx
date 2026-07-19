import { Mic, Radio, CheckCircle2, AlertTriangle, Loader2, RotateCcw, Info, FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusPill } from "./StatusPill";
import { useEffect, useRef, useState } from "react";
import { useCreateJobFromVoice } from "@/lib/api/hooks";
import { setRuntimeMode, useRuntimeMode } from "@/api/client";
import { DEMO_JOB_ID } from "@/lib/api";
import type { IntakeVariant } from "@/lib/api/types";

type ConnState =
  | "ready"
  | "connecting"
  | "listening"
  | "processing"
  | "completed"
  | "failed";

const STATE_META: Record<ConnState, { label: string; tone: "neutral" | "info" | "verified" | "risk" | "caution" }> = {
  ready: { label: "Ready to connect", tone: "neutral" },
  connecting: { label: "Connecting to voice agent…", tone: "info" },
  listening: { label: "Listening", tone: "verified" },
  processing: { label: "Processing your answers…", tone: "info" },
  completed: { label: "Interview complete", tone: "verified" },
  failed: { label: "Interview failed", tone: "risk" },
};

// Scripted transcript that streams in during the demo "listening" phase so
// judges see the intake feels alive without any real audio being captured.
const DEMO_LINES: Array<{ speaker: "agent" | "you"; text: string }> = [
  { speaker: "agent", text: "Hi! I'm going to ask a few quick questions about your move. Where are you moving from and to?" },
  { speaker: "you", text: "Rock Hill, South Carolina to Charlotte, North Carolina." },
  { speaker: "agent", text: "Great. What's your target move date, and how flexible are you?" },
  { speaker: "you", text: "August 15th, 2026. I could do a day earlier or later." },
  { speaker: "agent", text: "Got it. Tell me about the home — bedrooms, floors, elevators?" },
  { speaker: "you", text: "Two-bedroom apartment. Origin is floor 2, no elevator. Destination is floor 4 with an elevator." },
  { speaker: "agent", text: "Any long carry from the truck to the door?" },
  { speaker: "you", text: "About 80 feet at the pickup." },
  { speaker: "agent", text: "Anything oversized or that needs disassembly?" },
  { speaker: "you", text: "One sofa, one queen bed that needs to come apart." },
];

const EXTRACTED_PREVIEW = [
  ["Route", "Rock Hill, SC → Charlotte, NC"],
  ["Date", "Aug 15, 2026 (±1 day)"],
  ["Home", "2 BR apartment"],
  ["Access", "Origin fl. 2 no elev · Dest fl. 4 elev"],
  ["Inventory", "Sofa, queen bed (disassembly)"],
];

export function VoiceIntakePanel({ onComplete }: { onComplete: (jobId: string) => void }) {
  const runtimeMode = useRuntimeMode();
  const [state, setState] = useState<ConnState>("ready");
  const [lines, setLines] = useState<typeof DEMO_LINES>([]);
  const [variant, setVariant] = useState<IntakeVariant>("clean");
  const timers = useRef<number[]>([]);
  const create = useCreateJobFromVoice();

  useEffect(() => {
    return () => {
      timers.current.forEach((t) => window.clearTimeout(t));
    };
  }, []);

  function clearTimers() {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  }

  function start() {
    clearTimers();
    setLines([]);
    setState("connecting");

    timers.current.push(
      window.setTimeout(() => setState("listening"), 900),
    );

    // Stream in the scripted transcript.
    DEMO_LINES.forEach((line, i) => {
      timers.current.push(
        window.setTimeout(() => {
          setLines((prev) => [...prev, line]);
        }, 1400 + i * 900),
      );
    });

    // Move to processing, then completed.
    timers.current.push(
      window.setTimeout(() => setState("processing"), 1400 + DEMO_LINES.length * 900),
    );
    timers.current.push(
      window.setTimeout(async () => {
        try {
          const { jobId } = await create.mutateAsync(variant);
          setState("completed");
          // Small pause so the user sees the completed state before nav.
          timers.current.push(
            window.setTimeout(() => onComplete(jobId), 700),
          );
        } catch {
          setState("failed");
        }
      }, 2100 + DEMO_LINES.length * 900),
    );
  }

  function retry() {
    clearTimers();
    setState("ready");
    setLines([]);
  }

  const meta = STATE_META[state];
  const isActive = state === "connecting" || state === "listening" || state === "processing";

  return (
    <section
      aria-label="Voice interview"
      className="flex h-full flex-col gap-5 rounded-2xl border border-border bg-surface p-6"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Voice interview</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Answer a short conversation with our AI intake agent. Takes about
            two minutes.
            {runtimeMode === "demo" && (
              <span className="ml-1 rounded bg-caution-soft px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-caution-foreground">
                Demo · role-play
              </span>
            )}
          </p>
        </div>
        <StatusPill tone={meta.tone}>
          {state === "listening" && <Radio className="h-3 w-3" aria-hidden />}
          {state === "processing" && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
          {state === "completed" && <CheckCircle2 className="h-3 w-3" aria-hidden />}
          {state === "failed" && <AlertTriangle className="h-3 w-3" aria-hidden />}
          {meta.label}
        </StatusPill>
      </header>

      {runtimeMode === "live" && (
        <div
          role="note"
          className="flex flex-col gap-2 rounded-lg border border-info/40 bg-info-soft p-3 text-sm sm:flex-row sm:items-start"
        >
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden />
          <div className="flex-1">
            <p className="font-medium">Live voice intake is being connected.</p>
            <p className="text-muted-foreground">
              Use document intake or Demo Mode today.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5 self-start"
            onClick={() =>
              setRuntimeMode("demo", { redirectTo: `/confirm/${DEMO_JOB_ID}` })
            }
          >
            <FlaskConical className="h-3.5 w-3.5" />
            Switch to Demo
          </Button>
        </div>
      )}

      <div
        role="status"
        aria-live="polite"
        aria-atomic="false"
        className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-surface-muted py-8"
      >
        <div
          aria-hidden
          className={
            "flex h-16 w-16 items-center justify-center rounded-full transition-colors " +
            (state === "listening"
              ? "bg-verified text-verified-foreground"
              : state === "failed"
                ? "bg-risk text-risk-foreground"
                : "bg-primary text-primary-foreground")
          }
        >
          {state === "listening" ? (
            <Radio className="h-6 w-6 animate-pulse" />
          ) : state === "failed" ? (
            <AlertTriangle className="h-6 w-6" />
          ) : (
            <Mic className="h-6 w-6" />
          )}
        </div>
        <p className="text-sm text-muted-foreground">{meta.label}</p>
      </div>

      {/* Transcript preview */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Live transcript
          </h4>
          {lines.length > 0 && (
            <span className="text-xs text-muted-foreground">{lines.length} turns</span>
          )}
        </div>
        <div
          className="max-h-40 overflow-y-auto rounded-lg border border-border bg-surface-muted p-3 text-sm"
          aria-live="polite"
        >
          {lines.length === 0 ? (
            <p className="text-muted-foreground">
              Transcript will appear here once the interview begins.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {lines.map((l, i) => (
                <li key={i} className="flex gap-2">
                  <span
                    className={
                      "shrink-0 text-xs font-medium uppercase tracking-wide " +
                      (l.speaker === "agent" ? "text-primary" : "text-muted-foreground")
                    }
                  >
                    {l.speaker === "agent" ? "Agent" : "You"}
                  </span>
                  <span className="text-foreground">{l.text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Extracted-field preview once processing/completed */}
      {(state === "processing" || state === "completed") && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Extracted so far
          </h4>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-1 rounded-lg border border-verified/30 bg-verified-soft p-3 text-sm sm:grid-cols-2">
            {EXTRACTED_PREVIEW.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2 sm:block">
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {k}
                </dt>
                <dd className="text-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Demo variant selector so judges can trigger the missing/warning states. */}
      <fieldset className="rounded-lg border border-dashed border-border p-3">
        <legend className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Demo variant
        </legend>
        <div className="flex flex-wrap gap-3 text-sm">
          {(["clean", "missing", "warnings"] as IntakeVariant[]).map((v) => (
            <label key={v} className="flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                name="voice-variant"
                value={v}
                checked={variant === v}
                onChange={() => setVariant(v)}
                disabled={isActive}
                className="accent-primary"
              />
              <span className="capitalize">{v}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
        {state === "failed" ? (
          <Button onClick={retry} variant="outline" className="gap-1.5">
            <RotateCcw className="h-4 w-4" /> Retry interview
          </Button>
        ) : (
          <Button
            onClick={start}
            disabled={isActive || state === "completed" || runtimeMode === "live"}
            className="gap-1.5"
            title={runtimeMode === "live" ? "Live voice intake is being connected" : undefined}
          >
            <Mic className="h-4 w-4" />
            {state === "ready" ? "Start voice interview" : meta.label}
          </Button>
        )}
        {state === "completed" && (
          <span className="text-sm text-muted-foreground">Taking you to review…</span>
        )}
      </div>
    </section>
  );
}
