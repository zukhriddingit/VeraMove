import { Mic, MicOff } from "lucide-react";
import type { RecordingView } from "@/lib/api/types";

/**
 * Renders a real <audio> element ONLY when the backend supplies a valid
 * recording URL. Otherwise renders a disabled indicator; never fabricates
 * a fake player.
 */
export function RecordingPlayer({
  recording,
  className,
}: {
  recording?: RecordingView | null;
  className?: string;
}) {
  if (!recording?.url) {
    return (
      <div
        className={
          "inline-flex items-center gap-1.5 rounded-md border border-dashed border-border px-2 py-1 text-xs text-muted-foreground " +
          (className ?? "")
        }
      >
        <MicOff className="h-3.5 w-3.5" aria-hidden />
        <span>RecordingView unavailable</span>
      </div>
    );
  }
  return (
    <div className={"flex flex-col gap-1 " + (className ?? "")}>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Mic className="h-3.5 w-3.5" aria-hidden />
        <span>
          Call recording
          {recording.durationSec
            ? ` · ${Math.round(recording.durationSec / 60)} min`
            : ""}
        </span>
      </div>
      <audio
        controls
        preload="none"
        src={recording.url}
        aria-label="Call recording"
        className="w-full max-w-sm"
      />
    </div>
  );
}
