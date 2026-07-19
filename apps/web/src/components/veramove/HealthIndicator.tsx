import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useRuntimeMode } from "@/api/client";
import { cn } from "@/lib/utils";
import { Loader2, CheckCircle2, AlertTriangle, WifiOff, RotateCcw, MinusCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export type HealthState =
  | "idle"
  | "checking"
  | "starting_backend"
  | "online"
  | "degraded"
  | "offline";

/**
 * Polls /health and surfaces cold-start awareness. Render hidden in demo
 * mode — there's no live backend to probe.
 *
 * State machine:
 *   idle → checking → (waiting > 2.5s) → starting_backend → online / degraded / offline
 *
 * The label deliberately changes from "Checking API…" to
 * "Starting secure backend…" once we suspect a Render cold start, so the user
 * knows why the first request is slow without us prematurely calling it
 * offline.
 */
export function HealthIndicator({ onUseDemo }: { onUseDemo?: () => void }) {
  const isDemoMode = useRuntimeMode() === "demo";
  const [firstAttemptAt] = useState(() => Date.now());
  const q = useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth?.() ?? Promise.resolve({ status: "ok" as const }),
    enabled: !isDemoMode,
    refetchInterval: (query) => (query.state.data ? 30_000 : 4_000),
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 6_000),
    staleTime: 10_000,
  });

  const [state, setState] = useState<HealthState>(isDemoMode ? "online" : "idle");

  useEffect(() => {
    if (isDemoMode) return;
    if (q.data) {
      setState("online");
      return;
    }
    if (q.isFetching) {
      const elapsed = Date.now() - firstAttemptAt;
      // Under ~2.5s it's normal latency; after that assume a Render cold
      // start and change the label so the user isn't left wondering.
      setState(elapsed > 2_500 ? "starting_backend" : "checking");
      return;
    }
    if (q.isError) {
      const elapsed = Date.now() - firstAttemptAt;
      // Give the cold start a full 20s before we say "offline".
      setState(elapsed < 20_000 ? "starting_backend" : "offline");
    }
  }, [q.isFetching, q.data, q.isError, firstAttemptAt]);

  if (isDemoMode) return null;

  const meta = STATE_META[state];
  const Icon = meta.icon;
  const showActions = state === "offline" || state === "degraded";

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium",
        meta.className,
      )}
    >
      <Icon
        className={cn(
          "h-3.5 w-3.5",
          state === "checking" || state === "starting_backend" ? "animate-spin" : "",
        )}
        aria-hidden
      />
      <span>{meta.label}</span>
      {showActions && (
        <>
          <Button
            variant="ghost"
            size="sm"
            className="ml-1 h-6 gap-1 px-2 text-xs"
            onClick={() => q.refetch()}
          >
            <RotateCcw className="h-3 w-3" /> Retry
          </Button>
          {onUseDemo && (
            <Button variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={onUseDemo}>
              Use demo
            </Button>
          )}
        </>
      )}
    </div>
  );
}

const STATE_META: Record<HealthState, {
  label: string;
  icon: typeof Loader2;
  className: string;
}> = {
  idle: {
    label: "API idle",
    icon: MinusCircle,
    className: "border-border bg-surface text-muted-foreground",
  },
  checking: {
    label: "Checking API…",
    icon: Loader2,
    className: "border-border bg-surface text-muted-foreground",
  },
  starting_backend: {
    label: "Starting secure backend…",
    icon: Loader2,
    className: "border-info/40 bg-info-soft text-foreground",
  },
  online: {
    label: "API online",
    icon: CheckCircle2,
    className: "border-verified/40 bg-verified-soft text-verified",
  },
  degraded: {
    label: "API degraded",
    icon: AlertTriangle,
    className: "border-caution/50 bg-caution-soft text-caution-foreground",
  },
  offline: {
    label: "API unreachable",
    icon: WifiOff,
    className: "border-risk/40 bg-risk-soft text-risk",
  },
};
