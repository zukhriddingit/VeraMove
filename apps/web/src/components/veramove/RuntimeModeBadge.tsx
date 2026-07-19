import { setRuntimeMode, useRuntimeMode } from "@/api/client";
import { FlaskConical, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Small pill that makes the current runtime mode unambiguous in the header.
 * Clicking toggles between Live and Demo — an explicit user action, never
 * an implicit fallback.
 */
export function RuntimeModeBadge({ className }: { className?: string }) {
  const isDemo = useRuntimeMode() === "demo";
  const next = isDemo ? "live" : "demo";
  const label = isDemo ? "Demo · synthetic data" : "Live · connected";
  const title = isDemo
    ? "Currently in Demo mode. Click to switch to Live (uses the FastAPI backend)."
    : "Currently in Live mode. Click to switch to Demo (seeded synthetic data).";
  return (
    <button
      type="button"
      onClick={() => setRuntimeMode(next)}
      title={title}
      aria-label={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        isDemo
          ? "border-caution/40 bg-caution-soft text-caution-foreground hover:bg-caution-soft/70"
          : "border-verified/40 bg-verified-soft text-foreground hover:bg-verified-soft/70",
        className,
      )}
    >
      {isDemo ? (
        <FlaskConical className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Zap className="h-3.5 w-3.5" aria-hidden />
      )}
      <span>{label}</span>
    </button>
  );
}
