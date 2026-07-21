import { useMemo, useState } from "react";
import type { JobVendorResearchV1, VendorCallAuthorizationSelectionV1 } from "@/api/client";
import { useClearVendorCallAuthorizations, useSaveVendorCallAuthorizations } from "@/lib/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AlertTriangle, CheckCircle2, ExternalLink, LoaderCircle, PhoneCall } from "lucide-react";

type Dossier = NonNullable<JobVendorResearchV1["dossiers"]>[number];
type Contact = NonNullable<Dossier["contact_candidates"]>[number];
type IdentifiedContact = Contact & { contact_id: string };
type ConsentMethod = VendorCallAuthorizationSelectionV1["consent_method"];

type DraftSelection = {
  contactId: string;
  timezone: string;
  consentMethod: ConsentMethod;
  evidenceReference: string;
  consentedAt: string;
  aiConsented: boolean;
  recordingConsented: boolean;
};

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
] as const;

function availableContacts(dossier: Dossier): IdentifiedContact[] {
  return (dossier.contact_candidates ?? []).filter((contact): contact is IdentifiedContact =>
    Boolean(contact.contact_id),
  );
}

function freshSelection(): DraftSelection {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
  return {
    contactId: "",
    timezone: "America/New_York",
    consentMethod: "direct_recipient_opt_in",
    evidenceReference: "",
    consentedAt: local,
    aiConsented: false,
    recordingConsented: false,
  };
}

export function VendorContactReview({
  jobId,
  research,
  onStartCalls,
  startPending,
  canStartCalls,
}: {
  jobId: string;
  research: JobVendorResearchV1;
  onStartCalls: () => void;
  startPending: boolean;
  canStartCalls: boolean;
}) {
  const dossiers = research.dossiers ?? [];
  const save = useSaveVendorCallAuthorizations();
  const clear = useClearVendorCallAuthorizations();
  const [drafts, setDrafts] = useState<Record<string, DraftSelection>>(() =>
    Object.fromEntries(dossiers.map((dossier) => [dossier.vendor.vendor_id, freshSelection()])),
  );
  const [consentAcknowledged, setConsentAcknowledged] = useState(false);
  const [startAcknowledged, setStartAcknowledged] = useState(false);

  const plansByVendor = useMemo(
    () => new Map((research.call_plans ?? []).map((plan) => [plan.vendor_id, plan])),
    [research.call_plans],
  );
  const existingByVendor = useMemo(
    () =>
      new Map(
        (research.call_authorizations ?? []).map((authorization) => [
          authorization.vendor_id,
          authorization,
        ]),
      ),
    [research.call_authorizations],
  );
  const allContactsAvailable =
    dossiers.length === 3 && dossiers.every((dossier) => availableContacts(dossier).length > 0);
  const draftsReady =
    allContactsAvailable &&
    dossiers.every((dossier) => {
      const item = drafts[dossier.vendor.vendor_id];
      return (
        !!item?.contactId &&
        !!item.timezone &&
        !!item.evidenceReference.trim() &&
        !!item.consentedAt &&
        item.aiConsented &&
        item.recordingConsented
      );
    });
  const busy = save.isPending || clear.isPending || startPending;
  const error = save.error ?? clear.error;

  const update = (vendorId: string, patch: Partial<DraftSelection>) => {
    setDrafts((current) => ({
      ...current,
      [vendorId]: { ...(current[vendorId] ?? freshSelection()), ...patch },
    }));
  };

  const authorize = async () => {
    if (!draftsReady || !consentAcknowledged) return;
    const selections = dossiers.map((dossier) => {
      const item = drafts[dossier.vendor.vendor_id];
      return {
        vendor_id: dossier.vendor.vendor_id,
        contact_id: item.contactId,
        recipient_timezone: item.timezone,
        consent_method: item.consentMethod,
        consent_evidence_reference: item.evidenceReference.trim(),
        consented_at: new Date(item.consentedAt).toISOString(),
        ai_call_consented: true as const,
        recording_consented: true as const,
      };
    });
    await save.mutateAsync({
      jobId,
      request: { selections, batch_acknowledged: true },
    });
  };

  return (
    <section className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">Review recipients and call plans</h3>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Website phone numbers are public contact data, not permission to call. Each recipient
            must separately opt in to this AI call and recording before VeraMove can dial.
          </p>
        </div>
        <Badge variant={research.authorization_ready ? "outline" : "secondary"}>
          {research.authorization_ready ? "3 recipients ready" : "Authorization required"}
        </Badge>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {dossiers.map((dossier) => (
          <RecipientCard
            key={dossier.vendor.vendor_id}
            dossier={dossier}
            draft={drafts[dossier.vendor.vendor_id] ?? freshSelection()}
            existing={existingByVendor.get(dossier.vendor.vendor_id)}
            plan={plansByVendor.get(dossier.vendor.vendor_id)}
            disabled={busy || research.authorization_ready || !canStartCalls}
            onChange={(patch) => update(dossier.vendor.vendor_id, patch)}
          />
        ))}
      </div>

      {!allContactsAvailable && (
        <p className="mt-4 flex items-start gap-2 rounded-lg border border-risk/30 bg-risk-soft p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-risk" />
          Every selected mover needs a phone number found on its official website. Replace or retry
          any mover without one.
        </p>
      )}

      {!research.authorization_ready && canStartCalls && (
        <div className="mt-4 space-y-3 border-t border-border pt-4">
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              checked={consentAcknowledged}
              onCheckedChange={(checked) => setConsentAcknowledged(checked === true)}
              disabled={busy}
              aria-label="Confirm all three recipients opted in"
            />
            <span>
              I confirm these three recipients affirmatively opted in to an AI-generated quote
              request and recording. None of these boxes were preselected.
            </span>
          </label>
          <Button
            onClick={() => void authorize()}
            disabled={!draftsReady || !consentAcknowledged || busy}
          >
            {save.isPending ? <LoaderCircle className="animate-spin" /> : <CheckCircle2 />}
            Save three authorizations
          </Button>
        </div>
      )}

      {!research.authorization_ready && !canStartCalls && (
        <p className="mt-4 flex items-center gap-2 border-t border-border pt-4 text-sm text-muted-foreground">
          <AlertTriangle className="h-4 w-4 text-risk" />
          Dispatch has already started, so recipient authorization can no longer be changed.
        </p>
      )}

      {research.authorization_ready && canStartCalls && (
        <div className="mt-4 space-y-3 border-t border-border pt-4">
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              checked={startAcknowledged}
              onCheckedChange={(checked) => setStartAcknowledged(checked === true)}
              disabled={busy}
              aria-label="Acknowledge exactly three calls will start"
            />
            <span>
              Start exactly three AI calls now using the same locked move specification and the
              reviewed recipient-specific plans above.
            </span>
          </label>
          <div className="flex flex-wrap gap-2">
            <Button disabled={!startAcknowledged || busy} onClick={onStartCalls}>
              {startPending ? <LoaderCircle className="animate-spin" /> : <PhoneCall />}
              {startPending ? "Starting three calls…" : "Start three authorized calls"}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => clear.mutate(jobId)}>
              Change recipients
            </Button>
          </div>
        </div>
      )}

      {research.authorization_ready && !canStartCalls && (
        <p className="mt-4 flex items-center gap-2 border-t border-border pt-4 text-sm text-muted-foreground">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          Recipients and call plans are locked because dispatch has already started.
        </p>
      )}

      {error && (
        <p className="mt-3 rounded-lg border border-risk/30 bg-risk-soft p-3 text-sm">
          {(error as Error).message}
        </p>
      )}
    </section>
  );
}

function RecipientCard({
  dossier,
  draft,
  existing,
  plan,
  disabled,
  onChange,
}: {
  dossier: Dossier;
  draft: DraftSelection;
  existing: NonNullable<JobVendorResearchV1["call_authorizations"]>[number] | undefined;
  plan: NonNullable<JobVendorResearchV1["call_plans"]>[number] | undefined;
  disabled: boolean;
  onChange: (patch: Partial<DraftSelection>) => void;
}) {
  return (
    <article className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <h4 className="font-semibold">{dossier.vendor.name}</h4>
        {existing && (
          <Badge variant={existing.ready ? "outline" : "destructive"}>
            {existing.ready ? "Ready" : existing.blocking_reason?.replaceAll("_", " ")}
          </Badge>
        )}
      </div>

      <RadioGroup
        className="mt-3 gap-2"
        value={existing?.contact_id ?? draft.contactId}
        onValueChange={(contactId) => onChange({ contactId })}
        disabled={disabled}
      >
        {availableContacts(dossier).map((contact) => (
          <div key={contact.contact_id} className="flex items-start gap-2 rounded-lg border p-2.5">
            <RadioGroupItem value={contact.contact_id} id={`contact-${contact.contact_id}`} />
            <Label htmlFor={`contact-${contact.contact_id}`} className="min-w-0 flex-1 font-normal">
              <span className="block font-medium">{contact.display_number}</span>
              <a
                href={contact.source_url}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground underline"
              >
                Official source <ExternalLink className="h-3 w-3" />
              </a>
            </Label>
          </div>
        ))}
      </RadioGroup>

      {!existing && (
        <div className="mt-3 space-y-3">
          <div className="space-y-1.5">
            <Label>Recipient timezone</Label>
            <Select
              value={draft.timezone}
              onValueChange={(timezone) => onChange({ timezone })}
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIMEZONES.map((timezone) => (
                  <SelectItem key={timezone} value={timezone}>
                    {timezone}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>How consent was obtained</Label>
            <Select
              value={draft.consentMethod}
              onValueChange={(value) => onChange({ consentMethod: value as ConsentMethod })}
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="direct_recipient_opt_in">Direct recipient opt-in</SelectItem>
                <SelectItem value="existing_business_relationship_confirmation">
                  Existing relationship confirmation
                </SelectItem>
                <SelectItem value="provider_test_destination">Owned test destination</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`evidence-${dossier.vendor.vendor_id}`}>Consent record reference</Label>
            <Input
              id={`evidence-${dossier.vendor.vendor_id}`}
              value={draft.evidenceReference}
              onChange={(event) => onChange({ evidenceReference: event.target.value })}
              placeholder="consent:record:001"
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`consented-${dossier.vendor.vendor_id}`}>Opt-in time</Label>
            <Input
              id={`consented-${dossier.vendor.vendor_id}`}
              type="datetime-local"
              value={draft.consentedAt}
              onChange={(event) => onChange({ consentedAt: event.target.value })}
              disabled={disabled}
            />
          </div>
          <label className="flex items-start gap-2 text-xs">
            <Checkbox
              checked={draft.aiConsented}
              onCheckedChange={(checked) => onChange({ aiConsented: checked === true })}
              disabled={disabled}
              aria-label={`Recipient at ${dossier.vendor.name} affirmatively opted in to an AI call`}
            />
            Recipient affirmatively opted in to an AI-generated call.
          </label>
          <label className="flex items-start gap-2 text-xs">
            <Checkbox
              checked={draft.recordingConsented}
              onCheckedChange={(checked) => onChange({ recordingConsented: checked === true })}
              disabled={disabled}
              aria-label={`Recipient at ${dossier.vendor.name} affirmatively opted in to recording`}
            />
            Recipient affirmatively opted in to recording and ElevenLabs processing.
          </label>
        </div>
      )}

      {plan && (
        <div className="mt-4 border-t border-border pt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Targeted call plan · {plan.questions.length} questions
          </p>
          <ol className="mt-2 space-y-1.5 text-xs">
            {plan.questions.slice(0, 4).map((question) => (
              <li key={question.question_id}>• {question.question}</li>
            ))}
          </ol>
          {plan.questions.length > 4 && (
            <p className="mt-1 text-xs text-muted-foreground">
              +{plan.questions.length - 4} more required checks
            </p>
          )}
        </div>
      )}
    </article>
  );
}
