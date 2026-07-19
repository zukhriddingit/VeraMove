import type { RequirementId, RequirementState, CallView } from "@/lib/api";
import { EvidenceBadge } from "./ConversationChecklist";
import { cn } from "@/lib/utils";

const REQUIREMENT_ROWS: { id: RequirementId; label: string; stageNote?: string }[] = [
  { id: "ai_disclosure", label: "AI disclosure" },
  { id: "friction_handled", label: "Friction handled" },
  {
    id: "verified_leverage",
    label: "Verified leverage only",
    stageNote: "May remain unobserved until the negotiation stage.",
  },
  { id: "structured_ending", label: "Structured ending" },
];

function stateLabel(s: RequirementState) {
  if (s === "passed") return "Passed";
  if (s === "failed") return "Failed";
  return "Not yet observed";
}

/**
 * Dashboard-level aggregation of the four conversation requirements across
 * the three vendor calls. Each cell shows per-call state with evidence.
 * Never marks a row "passed" without backend evidence — pending stays pending.
 */
export function CallsRequirementsChecklist({ calls }: { calls: CallView[] }) {
  return (
    <section
      className="rounded-2xl border border-border bg-surface p-5"
      aria-labelledby="conv-req-heading"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 id="conv-req-heading" className="text-base font-semibold">
          Conversation trust checklist
        </h3>
        <span className="text-xs text-muted-foreground">Across all three calls</span>
      </div>
      <ul className="mt-4 divide-y divide-border/70">
        {REQUIREMENT_ROWS.map((row) => (
          <li key={row.id} className="py-3">
            <div className="flex items-baseline justify-between gap-3">
              <div>
                <div className="text-sm font-medium">{row.label}</div>
                {row.stageNote && (
                  <div className="text-xs text-muted-foreground">{row.stageNote}</div>
                )}
              </div>
            </div>
            <div className="mt-2 grid gap-2 md:grid-cols-3">
              {calls.map((c) => {
                const req = c.requirements.find((r) => r.id === row.id);
                const state: RequirementState = req?.state ?? "pending";
                return (
                  <div
                    key={c.id}
                    className={cn(
                      "rounded-lg border p-2.5",
                      state === "passed" && "border-verified/30 bg-verified-soft",
                      state === "failed" && "border-risk/30 bg-risk-soft",
                      state === "pending" && "border-border bg-surface-muted",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium">{c.vendor.name}</span>
                      <EvidenceBadge state={state} />
                    </div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {stateLabel(state)}
                      {req?.evidence?.ts && req.evidence.ts !== "—" && (
                        <> · {req.evidence.ts}</>
                      )}
                    </div>
                    {req?.evidence?.excerpt && state !== "pending" && (
                      <div className="mt-1 line-clamp-2 text-[11px] text-foreground/80">
                        “{req.evidence.excerpt}”
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
