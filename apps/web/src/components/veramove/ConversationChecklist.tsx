import type { RequirementView } from "@/lib/api";
import { Check, X, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

function iconFor(state: RequirementView["state"]) {
  if (state === "passed") return <Check className="h-3.5 w-3.5" />;
  if (state === "failed") return <X className="h-3.5 w-3.5" />;
  return <Minus className="h-3.5 w-3.5" />;
}

export function EvidenceBadge({ state }: { state: RequirementView["state"] }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 w-5 items-center justify-center rounded-full",
        state === "passed" && "bg-verified text-verified-foreground",
        state === "failed" && "bg-risk text-risk-foreground",
        state === "pending" && "bg-muted text-muted-foreground",
      )}
      aria-label={state}
    >
      {iconFor(state)}
    </span>
  );
}

export function ConversationChecklist({
  requirements,
}: {
  requirements: RequirementView[];
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Conversation requirements
      </div>
      <ul className="mt-3 space-y-3">
        {requirements.map((r) => (
          <li key={r.id} className="flex gap-3">
            <EvidenceBadge state={r.state} />
            <div className="flex-1">
              <div className="flex items-center justify-between gap-2 text-sm font-medium">
                <span>{r.label}</span>
                <span
                  className={cn(
                    "text-xs font-normal",
                    r.state === "passed" && "text-verified",
                    r.state === "failed" && "text-risk",
                    r.state === "pending" && "text-muted-foreground",
                  )}
                >
                  {r.state === "passed"
                    ? "Passed"
                    : r.state === "failed"
                      ? "Failed"
                      : "Not yet observed"}
                </span>
              </div>
              {r.evidence && (
                <div className="mt-1 rounded-md bg-muted/70 p-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">
                    {r.evidence.ts}
                  </span>{" "}
                  — {r.evidence.excerpt}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
