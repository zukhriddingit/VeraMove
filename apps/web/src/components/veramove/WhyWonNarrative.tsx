import type { ReportNarrativeView } from "@/lib/api/types";
import { BookOpen } from "lucide-react";

const SECTIONS: Array<{ key: keyof ReportNarrativeView; heading: string }> = [
  { key: "whyThisVendor", heading: "Why this vendor" },
  { key: "whyNotCheapest", heading: "Why not simply choose the cheapest" },
  { key: "whatChanged", heading: "What changed during negotiation" },
  { key: "remainingUncertainty", heading: "Remaining uncertainty" },
  { key: "whatToVerify", heading: "What to verify before booking" },
];

/**
 * Renders the backend's grounded narrative sections verbatim. No local
 * generation — OpenAI runs behind the backend only.
 */
export function WhyWonNarrative({
  narrative,
}: {
  narrative?: ReportNarrativeView | null;
}) {
  const present = SECTIONS.filter((s) => (narrative?.[s.key] ?? "").trim().length > 0);
  if (!narrative || present.length === 0) return null;

  return (
    <section
      aria-labelledby="why-won-title"
      className="rounded-2xl border border-border bg-surface p-5"
    >
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <BookOpen className="h-3.5 w-3.5" aria-hidden />
        Why this vendor won
      </div>
      <h3 id="why-won-title" className="sr-only">
        Recommendation rationale
      </h3>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        {present.map((s) => (
          <div key={s.key}>
            <div className="text-sm font-medium">{s.heading}</div>
            <p className="mt-1 text-sm leading-relaxed text-foreground/90">
              {narrative[s.key]}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
