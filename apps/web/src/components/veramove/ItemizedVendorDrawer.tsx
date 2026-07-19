import type { RankedVendorView, CallView } from "@/lib/api/types";
import { usd } from "@/lib/format";
import { AlertTriangle, Sparkles } from "lucide-react";
import { RecordingPlayer } from "./RecordingPlayer";
import { TranscriptExcerpt } from "./TranscriptExcerpt";

/**
 * Full itemized breakdown for one vendor. Renders backend fields only —
 * no derived totals. Missing values show as "Not provided" / "Unknown".
 */
export function ItemizedVendorDrawer({
  vendor,
  call,
}: {
  vendor: RankedVendorView;
  call?: CallView;
}) {
  const fees = call?.fees ?? [];
  const hiddenFees = call?.hiddenFees ?? [];
  const evidenceLines = (call?.transcript ?? []).filter((l) => l.tag);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Left: totals + concessions + line items */}
      <div className="flex flex-col gap-4">
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="grid grid-cols-2 gap-y-1.5 text-sm">
            <Row label="Headline total" value={money(vendor.headlineTotal)} />
            <Row label="Verified total" value={money(vendor.verifiedTotal)} />
            <Row
              label="Negotiated total"
              value={money(vendor.negotiatedTotal)}
              emphasize
            />
            <Row
              label="Deposit"
              value={money(vendor.deposit)}
            />
            <Row
              label="Binding"
              value={vendor.binding ? "Yes" : "No"}
            />
            <Row
              label="Availability"
              value={vendor.availability ?? "Awaiting verification"}
            />
          </div>
        </div>

        {fees.length + hiddenFees.length > 0 && (
          <div className="rounded-lg border border-border bg-surface p-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Line items
            </div>
            <ul className="mt-2 space-y-1 text-sm">
              {fees.map((f, i) => (
                <li
                  key={`f-${i}`}
                  className="flex items-baseline justify-between gap-4"
                >
                  <span>
                    {f.label}
                    {f.note ? (
                      <span className="ml-1 text-xs text-muted-foreground">
                        · {f.note}
                      </span>
                    ) : null}
                  </span>
                  <span className="tabular-nums">{usd(f.amount)}</span>
                </li>
              ))}
              {hiddenFees.map((f, i) => (
                <li
                  key={`h-${i}`}
                  className="flex items-baseline justify-between gap-4 text-caution-foreground"
                >
                  <span className="inline-flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
                    {f.label}
                    <span className="text-[10px] uppercase tracking-wide">
                      revealed after probing
                    </span>
                  </span>
                  <span className="tabular-nums">{usd(f.amount)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {vendor.concessions && vendor.concessions.length > 0 && (
          <div className="rounded-lg border border-verified/30 bg-verified-soft p-3">
            <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-verified">
              <Sparkles className="h-3.5 w-3.5" aria-hidden />
              Concessions won
            </div>
            <ul className="mt-1.5 space-y-1 text-sm">
              {vendor.concessions.map((c, i) => (
                <li key={i}>• {c}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Right: warnings, evidence, recording */}
      <div className="flex flex-col gap-3">
        {vendor.warnings && vendor.warnings.length > 0 ? (
          <div className="rounded-lg border border-caution/40 bg-caution-soft p-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-caution-foreground">
              Warnings
            </div>
            <ul className="mt-1.5 space-y-1 text-sm text-caution-foreground">
              {vendor.warnings.map((w, i) => (
                <li key={i}>• {w}</li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="rounded-lg border border-border bg-surface-muted p-3 text-xs text-muted-foreground">
            No warnings supplied for this vendor.
          </div>
        )}

        {evidenceLines.length > 0 ? (
          <div className="flex flex-col gap-2">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Transcript evidence
            </div>
            {evidenceLines.slice(0, 3).map((l, i) => (
              <TranscriptExcerpt
                key={i}
                ts={l.ts}
                excerpt={l.text}
                vendorName={call?.vendor.name}
              />
            ))}
          </div>
        ) : (
          <p className="text-xs italic text-muted-foreground">
            Transcript evidence unavailable.
          </p>
        )}

        <RecordingPlayer recording={call?.recording ?? null} />
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  return (
    <>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={
          "text-right tabular-nums " + (emphasize ? "font-semibold" : "")
        }
      >
        {value}
      </div>
    </>
  );
}

function money(n?: number | null) {
  return n === undefined || n === null ? "Not provided" : usd(n);
}
