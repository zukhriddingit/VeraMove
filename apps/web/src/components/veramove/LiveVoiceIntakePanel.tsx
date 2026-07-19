import { useEffect, useMemo, useRef } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
  Loader2,
  Mic,
  PhoneOff,
  Radio,
  RotateCcw,
} from "lucide-react";
import { setRuntimeMode } from "@/api/client";
import { Button } from "@/components/ui/button";
import { useBrowserVoiceIntake } from "@/lib/voice/useBrowserVoiceIntake";
import { StatusPill } from "./StatusPill";

const STATE_META = {
  ready: { label: "Ready for live interview", tone: "neutral" },
  requesting_microphone: { label: "Requesting microphone…", tone: "info" },
  connecting: { label: "Connecting securely…", tone: "info" },
  connected: { label: "Live interview", tone: "verified" },
  processing: { label: "Structuring your move…", tone: "info" },
  delayed: { label: "Processing is delayed", tone: "caution" },
  completed: { label: "Interview complete", tone: "verified" },
  failed: { label: "Interview needs attention", tone: "risk" },
} as const;

export function LiveVoiceIntakePanel({ onComplete }: { onComplete: (jobId: string) => void }) {
  const voice = useBrowserVoiceIntake();
  const navigatedRef = useRef(false);
  const meta = STATE_META[voice.phase];
  const isActive = ["requesting_microphone", "connecting", "connected"].includes(voice.phase);

  useEffect(() => {
    if (
      navigatedRef.current ||
      voice.phase !== "completed" ||
      !voice.jobId ||
      !voice.jobSpec ||
      voice.jobSpec.intake_source !== "voice" ||
      voice.jobSpec.confirmed ||
      voice.jobSpec.confirmed_at ||
      voice.jobSpec.locked_version
    ) {
      return;
    }
    navigatedRef.current = true;
    const timer = window.setTimeout(() => onComplete(voice.jobId as string), 700);
    return () => window.clearTimeout(timer);
  }, [onComplete, voice.jobId, voice.jobSpec, voice.phase]);

  const preview = useMemo(() => {
    if (!voice.jobSpec) return [];
    const origin = voice.jobSpec.origin.address_summary || "Needs review";
    const destination = voice.jobSpec.destination.address_summary || "Needs review";
    const services = [
      voice.jobSpec.services?.packing ? "Packing" : null,
      voice.jobSpec.services?.disassembly ? "Disassembly" : null,
      voice.jobSpec.services?.storage ? "Storage" : null,
    ].filter(Boolean);
    return [
      ["Route", `${origin} → ${destination}`],
      ["Move date", voice.jobSpec.move_date || "Needs review"],
      [
        "Home",
        voice.jobSpec.bedroom_count ? `${voice.jobSpec.bedroom_count} bedroom` : "Needs review",
      ],
      ["Inventory", `${voice.jobSpec.inventory?.length ?? 0} captured items`],
      ["Services", services.join(", ") || "No extras captured"],
    ];
  }, [voice.jobSpec]);

  return (
    <section
      aria-label="Voice interview"
      className="flex h-full flex-col gap-5 rounded-2xl border border-border bg-surface p-6"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Voice interview</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Speak with VeraMove&apos;s live intake agent. Your answers become one structured move
            spec for review before any vendor call.
          </p>
        </div>
        <StatusPill tone={meta.tone}>
          {voice.phase === "connected" && <Radio className="h-3 w-3" aria-hidden />}
          {(["requesting_microphone", "connecting", "processing"] as string[]).includes(
            voice.phase,
          ) && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
          {voice.phase === "completed" && <CheckCircle2 className="h-3 w-3" aria-hidden />}
          {voice.phase === "failed" && <AlertTriangle className="h-3 w-3" aria-hidden />}
          {meta.label}
        </StatusPill>
      </header>

      <div className="rounded-lg border border-info/30 bg-info-soft p-3 text-xs text-muted-foreground">
        Use fictional demo move details only. Microphone audio is processed by ElevenLabs; VeraMove
        stores the resulting structured spec and provider evidence needed for the demo.
      </div>

      <div
        role="status"
        aria-live="polite"
        className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-surface-muted py-7"
      >
        <div
          aria-hidden
          className={`flex h-16 w-16 items-center justify-center rounded-full ${
            voice.phase === "connected"
              ? "bg-verified text-verified-foreground"
              : voice.phase === "failed"
                ? "bg-risk text-risk-foreground"
                : "bg-primary text-primary-foreground"
          }`}
        >
          {voice.phase === "connected" ? (
            <Radio className={`h-6 w-6 ${voice.isAgentSpeaking ? "animate-pulse" : ""}`} />
          ) : voice.phase === "failed" ? (
            <AlertTriangle className="h-6 w-6" />
          ) : (
            <Mic className="h-6 w-6" />
          )}
        </div>
        <p className="text-sm text-muted-foreground">{meta.label}</p>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Live transcript
          </h4>
          {voice.turns.length > 0 && (
            <span className="text-xs text-muted-foreground">{voice.turns.length} turns</span>
          )}
        </div>
        <div
          className="max-h-44 overflow-y-auto rounded-lg border border-border bg-surface-muted p-3 text-sm"
          aria-live="polite"
        >
          {voice.turns.length === 0 ? (
            <p className="text-muted-foreground">
              The real conversation transcript will appear after you connect.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {voice.turns.map((turn) => (
                <li key={turn.id} className="flex gap-2">
                  <span
                    className={`shrink-0 text-xs font-medium uppercase tracking-wide ${
                      turn.role === "agent" ? "text-primary" : "text-muted-foreground"
                    }`}
                  >
                    {turn.role === "agent" ? "Agent" : "You"}
                  </span>
                  <span>{turn.text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {preview.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Structured for review
          </h4>
          <dl className="grid grid-cols-1 gap-2 rounded-lg border border-verified/30 bg-verified-soft p-3 text-sm sm:grid-cols-2">
            {preview.map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {label}
                </dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {voice.error && (
        <p role="alert" className="rounded-lg border border-risk/30 bg-risk-soft p-3 text-sm">
          {voice.error}
        </p>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
        {voice.phase === "ready" && (
          <Button onClick={() => void voice.start()} className="gap-1.5">
            <Mic className="h-4 w-4" /> Start live voice interview
          </Button>
        )}
        {voice.phase === "connected" && (
          <Button onClick={voice.end} variant="destructive" className="gap-1.5">
            <PhoneOff className="h-4 w-4" /> End interview
          </Button>
        )}
        {voice.phase === "failed" && (
          <Button onClick={voice.reset} variant="outline" className="gap-1.5">
            <RotateCcw className="h-4 w-4" /> Retry interview
          </Button>
        )}
        {voice.phase === "delayed" && (
          <Button onClick={voice.retryResult} variant="outline" className="gap-1.5">
            <RotateCcw className="h-4 w-4" /> Check result again
          </Button>
        )}
        {(voice.phase === "failed" || voice.phase === "delayed") && (
          <Button
            onClick={() => setRuntimeMode("demo", { redirectTo: "/intake" })}
            variant="ghost"
            className="gap-1.5"
          >
            <FlaskConical className="h-4 w-4" /> Switch to Demo
          </Button>
        )}
        {isActive && voice.phase !== "connected" && (
          <span className="text-sm text-muted-foreground">Keep this tab open…</span>
        )}
        {voice.phase === "completed" && (
          <span className="text-sm text-muted-foreground">Taking you to review…</span>
        )}
      </div>
    </section>
  );
}
