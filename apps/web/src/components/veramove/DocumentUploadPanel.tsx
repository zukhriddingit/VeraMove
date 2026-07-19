import { UploadCloud, FileText, X, CheckCircle2, AlertTriangle, RotateCcw, Loader2, ClipboardPaste, FlaskConical, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { StatusPill } from "./StatusPill";
import { useEffect, useRef, useState } from "react";
import { useCreateJobFromDocument } from "@/lib/api/hooks";
import { runtimeMode, setRuntimeMode, ApiError } from "@/api/client";
import { createJobFromDocumentText } from "@/lib/api/endpoints";
import { DEMO_JOB_ID } from "@/lib/api";
import type { IntakeVariant } from "@/lib/api/types";

type UploadState =
  | "idle"
  | "validating"
  | "uploading"
  | "parsing"
  | "extracted"
  | "failed";

const ACCEPTED_MIME = ["application/pdf", "image/png", "image/jpeg"];
const ACCEPTED_EXT = [".pdf", ".png", ".jpg", ".jpeg"];
const MAX_BYTES = 15 * 1024 * 1024; // 15MB — sane cap for a demo upload.

function validate(file: File): string | null {
  const okMime = ACCEPTED_MIME.includes(file.type);
  const okExt = ACCEPTED_EXT.some((e) => file.name.toLowerCase().endsWith(e));
  if (!okMime && !okExt) return "Unsupported file type. Use PDF, PNG, or JPEG.";
  if (file.size > MAX_BYTES) return "File is larger than 15MB.";
  if (file.size === 0) return "File is empty.";
  return null;
}

const EXTRACTED_PREVIEW = [
  ["Route", "Rock Hill, SC → Charlotte, NC"],
  ["Date", "Aug 15, 2026"],
  ["Home", "2 BR apartment"],
  ["Access", "Origin fl. 2 · Dest fl. 4 elev · 80 ft carry"],
  ["Inventory", "Sofa, queen bed"],
];

export function DocumentUploadPanel({ onComplete }: { onComplete: (jobId: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<UploadState>("idle");
  const [progress, setProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [variant, setVariant] = useState<IntakeVariant>("clean");
  const timers = useRef<number[]>([]);
  const create = useCreateJobFromDocument();

  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  function reset() {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    setFile(null);
    setError(null);
    setState("idle");
    setProgress(0);
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleFile(f: File | null | undefined) {
    if (!f) return;
    setError(null);
    setState("validating");
    const err = validate(f);
    if (err) {
      setError(err);
      setFile(f);
      setState("failed");
      return;
    }
    setFile(f);
    startUpload(f);
  }

  function startUpload(f: File) {
    setState("uploading");
    setProgress(0);
    // Simulated upload progress. In live mode the fetch would report progress
    // via XHR; here we just animate for user feedback.
    let p = 0;
    const tick = window.setInterval(() => {
      p += Math.random() * 18 + 8;
      if (p >= 100) {
        p = 100;
        window.clearInterval(tick);
        setProgress(100);
        setState("parsing");
        timers.current.push(
          window.setTimeout(async () => {
            try {
              const { jobId } = await create.mutateAsync({ file: f, variant });
              setState("extracted");
              timers.current.push(window.setTimeout(() => onComplete(jobId), 800));
            } catch {
              setError("We couldn't parse this document. Try another file.");
              setState("failed");
            }
          }, 1200),
        );
      } else {
        setProgress(p);
      }
    }, 180);
    timers.current.push(tick as unknown as number);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (state === "uploading" || state === "parsing") return;
    handleFile(e.dataTransfer.files?.[0]);
  }

  const busy = state === "uploading" || state === "parsing" || state === "validating";

  const toneLabel: Record<UploadState, { label: string; tone: "neutral" | "info" | "verified" | "risk" }> = {
    idle: { label: "Ready to upload", tone: "neutral" },
    validating: { label: "Checking file…", tone: "info" },
    uploading: { label: "Uploading", tone: "info" },
    parsing: { label: "Parsing document…", tone: "info" },
    extracted: { label: "Extraction complete", tone: "verified" },
    failed: { label: "Upload failed", tone: "risk" },
  };
  const meta = toneLabel[state];

  // In live mode, the backend accepts document TEXT via /api/intake/document.
  // File upload is Demo-only for now.
  if (runtimeMode === "live") {
    return <LiveTextIntake onComplete={onComplete} />;
  }

  return (
    <section
      aria-label="Upload existing quote or inventory"
      className="flex h-full flex-col gap-5 rounded-2xl border border-border bg-surface p-6"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">
            Upload existing quote or inventory
            <span className="ml-2 rounded bg-caution-soft px-1.5 py-0.5 align-middle text-[10px] font-semibold uppercase tracking-wide text-caution-foreground">
              Demo · role-play
            </span>
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            PDF, PNG, or JPEG. Parsing is simulated in Demo Mode — file upload
            is not yet exposed by the live API.
          </p>
        </div>
        <StatusPill tone={meta.tone}>
          {state === "uploading" || state === "parsing" || state === "validating" ? (
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
          ) : state === "extracted" ? (
            <CheckCircle2 className="h-3 w-3" aria-hidden />
          ) : state === "failed" ? (
            <AlertTriangle className="h-3 w-3" aria-hidden />
          ) : null}
          {meta.label}
        </StatusPill>
      </header>

      {/* Drag-and-drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={
          "rounded-xl border border-dashed p-6 text-center transition-colors " +
          (dragOver
            ? "border-primary bg-primary/5"
            : "border-border bg-surface-muted")
        }
      >
        {file ? (
          <div className="flex flex-col items-center gap-3">
            <div className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-sm">
              <FileText className="h-4 w-4 text-muted-foreground" aria-hidden />
              <span className="font-medium">{file.name}</span>
              <span className="text-xs text-muted-foreground">
                {(file.size / 1024).toFixed(0)} KB
              </span>
              {!busy && (
                <button
                  type="button"
                  onClick={reset}
                  className="ml-1 rounded p-0.5 text-muted-foreground hover:bg-muted"
                  aria-label="Remove file"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            {(state === "uploading" || state === "parsing") && (
              <div className="w-full max-w-xs" aria-live="polite">
                <Progress value={state === "parsing" ? 100 : progress} />
                <p className="mt-1 text-xs text-muted-foreground">
                  {state === "uploading"
                    ? `Uploading… ${Math.round(progress)}%`
                    : "Parsing with OCR…"}
                </p>
              </div>
            )}
          </div>
        ) : (
          <label
            htmlFor="doc"
            className="flex cursor-pointer flex-col items-center gap-3"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <UploadCloud className="h-5 w-5" aria-hidden />
            </div>
            <div className="text-sm">
              <span className="font-medium text-foreground">Click to upload</span>
              <span className="text-muted-foreground"> or drag a file here</span>
            </div>
            <p className="text-xs text-muted-foreground">
              PDF, PNG, or JPEG · up to 15MB
            </p>
          </label>
        )}
        <input
          ref={inputRef}
          id="doc"
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          className="sr-only"
          onChange={(e) => handleFile(e.target.files?.[0])}
          disabled={busy}
        />
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-risk/30 bg-risk-soft p-3 text-sm"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-risk" aria-hidden />
          <div className="flex-1">
            <div className="font-medium">Couldn't use this file</div>
            <p className="text-muted-foreground">{error}</p>
          </div>
        </div>
      )}

      {state === "extracted" && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Extracted fields
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
          {variant === "warnings" && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-caution-foreground">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
              Some fields flagged for review on the next step.
            </p>
          )}
        </div>
      )}

      <fieldset className="rounded-lg border border-dashed border-border p-3">
        <legend className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Demo variant
        </legend>
        <div className="flex flex-wrap gap-3 text-sm">
          {(["clean", "missing", "warnings"] as IntakeVariant[]).map((v) => (
            <label key={v} className="flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                name="doc-variant"
                value={v}
                checked={variant === v}
                onChange={() => setVariant(v)}
                disabled={busy}
                className="accent-primary"
              />
              <span className="capitalize">{v}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
        {state === "failed" ? (
          <Button variant="outline" onClick={reset} className="gap-1.5">
            <RotateCcw className="h-4 w-4" /> Try another file
          </Button>
        ) : file && !busy && state !== "extracted" ? (
          <Button variant="outline" onClick={reset} className="gap-1.5">
            <RotateCcw className="h-4 w-4" /> Replace file
          </Button>
        ) : (
          <Button
            onClick={() => inputRef.current?.click()}
            disabled={busy}
            variant={file ? "outline" : "default"}
            className="gap-1.5"
          >
            <UploadCloud className="h-4 w-4" />
            {file ? "Choose different file" : "Choose file"}
          </Button>
        )}
        {state === "extracted" && (
          <span className="text-sm text-muted-foreground">Taking you to review…</span>
        )}
      </div>
    </section>
  );
}

// -------------------------------------------------------------------------
// Live-mode text intake — the canonical /api/intake/document endpoint accepts
// document text (paste from a quote, an inventory list, or move notes).
// -------------------------------------------------------------------------
function LiveTextIntake({ onComplete }: { onComplete: (jobId: string) => void }) {
  const [text, setText] = useState("");
  const [state, setState] = useState<"idle" | "parsing" | "extracted" | "failed">("idle");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string> | null>(null);

  const submit = async () => {
    setError(null);
    setFieldErrors(null);
    if (text.trim().length < 20) {
      setError("Paste at least a few sentences from your quote or inventory.");
      return;
    }
    setState("parsing");
    try {
      const { jobId } = await createJobFromDocumentText(text.trim());
      setState("extracted");
      setTimeout(() => onComplete(jobId), 600);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.detail);
        if (e.fieldErrors) setFieldErrors(e.fieldErrors);
      } else {
        setError(e instanceof Error ? e.message : "The backend couldn't parse this document.");
      }
      setState("failed");
    }
  };

  const busy = state === "parsing";

  return (
    <section
      aria-label="Paste document text"
      className="flex h-full flex-col gap-5 rounded-2xl border border-border bg-surface p-6"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Paste document text</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Paste an existing moving estimate, inventory list, or move notes.
            We extract the details and confirm them with you before any calls.
          </p>
        </div>
        <StatusPill
          tone={
            state === "extracted"
              ? "verified"
              : state === "failed"
                ? "risk"
                : busy
                  ? "info"
                  : "neutral"
          }
        >
          {busy && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
          {state === "extracted" && <CheckCircle2 className="h-3 w-3" aria-hidden />}
          {state === "failed" && <AlertTriangle className="h-3 w-3" aria-hidden />}
          {state === "idle" && "Ready"}
          {state === "parsing" && "Parsing…"}
          {state === "extracted" && "Extracted"}
          {state === "failed" && "Parse failed"}
        </StatusPill>
      </header>

      <div
        role="note"
        className="flex items-start gap-2 rounded-lg border border-info/40 bg-info-soft p-3 text-sm"
      >
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden />
        <p>
          File upload (PDF / PNG / JPEG) is not yet exposed by the current API.
          Paste document text instead — the backend endpoint
          <code className="mx-1 rounded bg-muted px-1 py-0.5 text-[11px]">POST /api/intake/document</code>
          accepts JSON text.
        </p>
      </div>

      <label htmlFor="doc-text" className="sr-only">
        Document text
      </label>
      <Textarea
        id="doc-text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste your moving estimate, inventory list, or move notes here…"
        rows={10}
        disabled={busy}
        aria-describedby={error ? "doc-text-err" : undefined}
        aria-invalid={state === "failed"}
        className="font-mono text-sm"
      />

      {error && (
        <div
          id="doc-text-err"
          role="alert"
          aria-live="polite"
          className="flex flex-col gap-2 rounded-lg border border-risk/30 bg-risk-soft p-3 text-sm"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-risk" aria-hidden />
            <p>{error}</p>
          </div>
          {fieldErrors && (
            <ul className="ml-6 list-disc space-y-0.5 text-xs text-muted-foreground">
              {Object.entries(fieldErrors).map(([path, msg]) => (
                <li key={path}>
                  <span className="font-mono">{path}</span>: {msg}
                </li>
              ))}
            </ul>
          )}
          <div className="ml-6">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() =>
                setRuntimeMode("demo", { redirectTo: `/confirm/${DEMO_JOB_ID}` })
              }
            >
              <FlaskConical className="h-3.5 w-3.5" />
              Load demo instead
            </Button>
          </div>
        </div>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
        <p className="text-xs text-muted-foreground">
          Aim for at least a few sentences of relevant detail.
        </p>
        <Button onClick={submit} disabled={busy || text.trim().length < 20} className="gap-1.5">
          <ClipboardPaste className="h-4 w-4" />
          {busy ? "Parsing…" : "Extract move details"}
        </Button>
      </div>
    </section>
  );
}
