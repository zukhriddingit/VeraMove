import type { RecordingView, TranscriptLineView } from "@/lib/api";
import { Play, Volume2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

function fmtSec(s: number) {
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function TranscriptExcerpt({ lines }: { lines: TranscriptLineView[] }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? lines : lines.slice(0, 3);
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Transcript excerpt
        </div>
        {lines.length > 3 && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-xs font-medium text-foreground hover:underline"
          >
            {expanded ? "Show less" : `Show all ${lines.length}`}
          </button>
        )}
      </div>
      <ol className="mt-3 space-y-2 text-sm">
        {shown.map((l, i) => (
          <li key={i} className="grid grid-cols-[52px_1fr] gap-3">
            <span className="tabular-nums text-xs text-muted-foreground">
              {l.ts}
            </span>
            <span>
              <span className="mr-1 font-medium capitalize">{l.speaker}:</span>
              <span className="text-foreground/90">{l.text}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function RecordingPlayer({ recording }: { recording?: RecordingView }) {
  // Only render a recording action when the backend actually supplies a URL.
  // Never fabricate a playable link.
  if (!recording || !recording.url) return null;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface-muted p-3 text-sm">
      <Button asChild size="icon" variant="outline" className="h-8 w-8" aria-label="Open call recording in new tab">
        <a href={recording.url} target="_blank" rel="noopener noreferrer">
          <Play className="h-3.5 w-3.5" />
        </a>
      </Button>
      <Volume2 className="h-4 w-4 text-muted-foreground" />
      <span className="text-muted-foreground">
        RecordingView · {fmtSec(recording.durationSec)}
      </span>
    </div>
  );
}
