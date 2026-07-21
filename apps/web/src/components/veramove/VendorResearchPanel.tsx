import { useEffect, useMemo, useState } from "react";
import type { JobVendorResearchV1 } from "@/api/client";
import {
  useAnalyzeVendorWebsites,
  useClearVendorShortlist,
  useDiscoverJobVendors,
  useSaveVendorShortlist,
  useVendorResearch,
} from "@/lib/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Globe2,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldQuestion,
} from "lucide-react";

type Candidate = JobVendorResearchV1["candidates"][number];
type Dossier = NonNullable<JobVendorResearchV1["dossiers"]>[number];

export function VendorResearchPanel({ jobId }: { jobId: string }) {
  const researchQ = useVendorResearch(jobId);
  const discover = useDiscoverJobVendors();
  const saveShortlist = useSaveVendorShortlist();
  const clearShortlist = useClearVendorShortlist();
  const analyze = useAnalyzeVendorWebsites();
  const research = researchQ.data;
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    if (research?.selected_vendor_ids?.length) {
      setSelected(research.selected_vendor_ids);
    }
  }, [research]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const hasSavedShortlist = (research?.selected_vendor_ids?.length ?? 0) === 3;
  const incompleteCount =
    research?.dossiers?.filter((dossier) => dossier.status !== "complete").length ?? 0;
  const busy =
    discover.isPending || saveShortlist.isPending || clearShortlist.isPending || analyze.isPending;
  const error = discover.error ?? saveShortlist.error ?? clearShortlist.error ?? analyze.error;

  const toggleCandidate = (vendorId: string, checked: boolean) => {
    setSelected((current) => {
      if (checked) {
        return current.includes(vendorId) || current.length === 3
          ? current
          : [...current, vendorId];
      }
      return current.filter((id) => id !== vendorId);
    });
  };

  const researchSelected = async () => {
    try {
      if (!hasSavedShortlist) {
        await saveShortlist.mutateAsync({ jobId, vendorIds: selected });
      }
      await analyze.mutateAsync({ jobId });
    } catch {
      // Mutation state renders the backend's normalized safe error below.
    }
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-5">
        <div className="flex gap-3">
          <div className="rounded-xl bg-emerald-500/10 p-2 text-emerald-700">
            <Search className="h-5 w-5" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold">Find and research real movers</h2>
              <Badge variant="outline" className="border-emerald-500/30 text-emerald-700">
                Tavily + OpenAI
              </Badge>
            </div>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Tavily finds movers for the locked route. Choose exactly three; only those websites
              are read. Published details become unverified leads, so the call confirms them once
              and asks from scratch only where information is missing.
            </p>
          </div>
        </div>
        {research && !hasSavedShortlist && (
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => discover.mutate({ jobId, refresh: true })}
          >
            <RefreshCw className={discover.isPending ? "animate-spin" : ""} />
            Refresh candidates
          </Button>
        )}
      </div>

      <div className="space-y-5 p-5">
        {!research && (
          <div className="rounded-xl border border-dashed border-border bg-surface-muted p-6 text-center">
            <Globe2 className="mx-auto h-6 w-6 text-muted-foreground" />
            <h3 className="mt-2 font-medium">Discover movers for this route</h3>
            <p className="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">
              No provider request runs until you start discovery. Only the route's city and
              state—not a street address—are sent to Tavily.
            </p>
            <Button className="mt-4" disabled={busy} onClick={() => discover.mutate({ jobId })}>
              {discover.isPending ? <LoaderCircle className="animate-spin" /> : <Search />}
              {discover.isPending ? "Finding movers…" : "Find real movers"}
            </Button>
          </div>
        )}

        {research && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <p className="text-muted-foreground">
                Search: {research.query.city}, {research.query.state} · within{" "}
                {research.query.radius_miles} miles
              </p>
              <p className="font-medium">{selected.length}/3 selected</p>
            </div>

            {!hasSavedShortlist && (
              <div className="grid gap-3 md:grid-cols-2">
                {research.candidates.map((vendor) => (
                  <CandidateCard
                    key={vendor.vendor_id}
                    vendor={vendor}
                    checked={selectedSet.has(vendor.vendor_id)}
                    disabled={!selectedSet.has(vendor.vendor_id) && selected.length === 3}
                    onCheckedChange={(checked) => toggleCandidate(vendor.vendor_id, checked)}
                  />
                ))}
              </div>
            )}

            {hasSavedShortlist && (
              <div className="grid gap-4 lg:grid-cols-3">
                {(research.dossiers ?? []).map((dossier) => (
                  <DossierCard key={dossier.vendor.vendor_id} dossier={dossier} />
                ))}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
              {!hasSavedShortlist && (
                <Button
                  disabled={selected.length !== 3 || busy}
                  onClick={() => void researchSelected()}
                >
                  {saveShortlist.isPending || analyze.isPending ? (
                    <LoaderCircle className="animate-spin" />
                  ) : (
                    <Globe2 />
                  )}
                  Research the selected three
                </Button>
              )}
              {hasSavedShortlist && incompleteCount > 0 && (
                <Button disabled={busy} onClick={() => analyze.mutate({ jobId })}>
                  {analyze.isPending ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
                  Research {incompleteCount} incomplete site
                  {incompleteCount === 1 ? "" : "s"}
                </Button>
              )}
              {hasSavedShortlist && incompleteCount === 0 && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => analyze.mutate({ jobId, refresh: true })}
                >
                  <RefreshCw className={analyze.isPending ? "animate-spin" : ""} />
                  Refresh website research
                </Button>
              )}
              {hasSavedShortlist && (
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => clearShortlist.mutate(jobId)}
                >
                  Change selected movers
                </Button>
              )}
              <p className="text-xs text-muted-foreground">
                Website claims never count as quote or transcript evidence.
              </p>
            </div>
          </>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-risk/30 bg-risk-soft p-3 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-risk" />
            <span>{(error as Error).message}</span>
          </div>
        )}
      </div>
    </section>
  );
}

function CandidateCard({
  vendor,
  checked,
  disabled,
  onCheckedChange,
}: {
  vendor: Candidate;
  checked: boolean;
  disabled: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  const sourceUrl = websiteUrl(vendor);
  return (
    <div className="flex gap-3 rounded-xl border border-border p-4 hover:bg-surface-muted">
      <Checkbox
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onCheckedChange(value === true)}
        aria-label={`Select ${vendor.name}`}
      />
      <span className="min-w-0 flex-1">
        <span className="block font-medium">{vendor.name}</span>
        <span className="mt-1 block text-xs text-muted-foreground">{vendor.service_areas[0]}</span>
        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => event.stopPropagation()}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium underline underline-offset-2"
          >
            Source website <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </span>
    </div>
  );
}

function DossierCard({ dossier }: { dossier: Dossier }) {
  const sourceUrl = websiteUrl(dossier.vendor);
  const claims = dossier.claims ?? [];
  const verificationQuestions = dossier.verification_questions ?? [];
  const questions = verificationQuestions.slice(0, 4);
  return (
    <article className="rounded-xl border border-border p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{dossier.vendor.name}</h3>
          {sourceUrl && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground underline"
            >
              Website <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
        <ResearchStatus status={dossier.status} />
      </div>

      {claims.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Published · unverified
          </div>
          <ul className="mt-2 space-y-2 text-sm">
            {claims.slice(0, 3).map((claim) => (
              <li key={claim.claim_id} className="rounded-lg bg-surface-muted p-2.5">
                {claim.summary}
                {(claim.qualifiers?.length ?? 0) > 0 && (
                  <span className="mt-1 block text-xs text-muted-foreground">
                    Conditions: {(claim.qualifiers ?? []).join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {questions.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <ShieldQuestion className="h-3.5 w-3.5" />
            Verify on the call
          </div>
          <ol className="mt-2 space-y-2 text-sm">
            {questions.map((question) => (
              <li key={question.question_id} className="flex gap-2">
                <span className="text-muted-foreground">•</span>
                <span>{question.question}</span>
              </li>
            ))}
          </ol>
          {(dossier.missing_fee_categories?.length ?? 0) > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              Missing from website:{" "}
              {(dossier.missing_fee_categories ?? [])
                .map((category) => category.replaceAll("_", " "))
                .join(", ")}
            </p>
          )}
          {verificationQuestions.length > questions.length && (
            <p className="mt-2 text-xs text-muted-foreground">
              +{verificationQuestions.length - questions.length} more targeted checks in the call
              plan
            </p>
          )}
        </div>
      )}

      {dossier.safe_failure_reason && (
        <p className="mt-4 rounded-lg bg-risk-soft p-2.5 text-xs">{dossier.safe_failure_reason}</p>
      )}
    </article>
  );
}

function ResearchStatus({ status }: { status: Dossier["status"] }) {
  const labels = {
    pending: "Not researched",
    complete: "Ready",
    partial: "Partial",
    failed: "Retry needed",
  } as const;
  return <Badge variant={status === "failed" ? "destructive" : "outline"}>{labels[status]}</Badge>;
}

function websiteUrl(vendor: Candidate): string | undefined {
  return (
    (vendor.provenance ?? []).find(
      (source) => source.source_type === "tavily" && source.location?.startsWith("https://"),
    )?.location ?? undefined
  );
}
