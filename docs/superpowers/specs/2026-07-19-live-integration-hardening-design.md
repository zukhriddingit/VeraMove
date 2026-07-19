# VeraMove Live Integration Hardening Design

**Date:** 2026-07-19  
**Status:** Approved for implementation  
**Scope:** OpenAI document-result normalization, role-play mock outcomes for Tavily-discovered vendors, and call-failure recovery.

## Goal

Make the simultaneously enabled OpenAI, Tavily, and Supabase configuration complete the mock demonstration workflow without weakening VeraMove's locked-JobSpec, evidence, provenance, or honesty requirements.

The deployed configuration must support:

1. OpenAI document intake that returns an unconfirmed `JobSpecV1` and persists it through Supabase.
2. Tavily discovery that returns provenance-bearing vendor candidates.
3. Exactly three mock initial calls to the first three distinct discovered vendors, all using the same locked JobSpec version.
4. Clearly labeled role-play quotes, evidence, and recording URLs that are not presented as claims about the discovered companies.
5. A job and call attempt that move to `failed` instead of remaining partially stuck in `calling` when a synchronous mock or provider call fails.

## Constraints

- `APP_MODE=mock` remains credential-free when all live-integration flags are disabled.
- OpenAI, Tavily, and Supabase remain independently enabled and fail closed.
- Exactly three initial mock calls must use one confirmed JobSpec snapshot.
- Tavily results supply names, URLs, service areas, and provenance only. They do not supply behavior, prices, quote evidence, or verified leverage.
- A simulated outcome for a Tavily-discovered vendor must use `data_classification=role_play` and explicitly state that it is not a factual claim about the company.
- Simulated calls use only `example.com` recording URLs and synthetic conversation/provider identifiers.
- No production phone call is activated by these changes. `APP_MODE=mock` continues to select `MockVoiceProvider`.
- No real contact details, phone numbers, customer PII, raw transcripts, or recordings are persisted.
- OpenAI may extract facts, but deterministic application code owns the canonical `missing_fields` list.
- Existing public route paths and Pydantic response contracts remain unchanged.

## Approaches Considered

### Fixture vendors only

Keep the three existing synthetic fixture vendors for mock calls and expose Tavily only through vendor discovery. This has the strongest separation between research and simulation, but it does not exercise Tavily candidates in the call orchestration path.

### Generic role-play outcomes for discovered vendors

Allow `MockVoiceProvider` to accept any normalized vendor. It returns a deterministic, neutral, explicitly role-play quote derived from a synthetic template and rebinds all canonical identifiers to the current job, vendor, and call. This is the selected approach.

### Reject unfamiliar vendors

Preserve the current `ResourceNotFound` behavior for vendors absent from demo fixtures. This is fail-closed but makes the all-enabled configuration unusable and can leave a workflow partially advanced.

## Architecture

### OpenAI normalization

`OpenAIDocumentParser` continues to request the strict `DocumentParseResult` JSON schema. The response remains untrusted.

The parser performs two deterministic stages:

1. Validate `response["job_spec"]` as `JobSpecV1`.
2. Copy the response, replace `missing_fields` with `job_spec.missing_required_fields()`, and validate the complete copy as `DocumentParseResult`.

This preserves model-produced warnings, confirmation fields, and provenance while preventing a semantically correct extraction from failing only because the model enumerated missing fields differently. Existing safety checks still reject voice intake, confirmed output, or a locked version.

Malformed envelopes, invalid JobSpecs, missing `job_spec`, refusals, and provider errors remain safe provider failures; normalization never supplies missing job facts.

### Generic Tavily-vendor role play

`MockVoiceProvider.initiate_quote_call` first looks for the existing exact synthetic fixture quote. Existing fixture-vendor behavior remains unchanged.

For an unfamiliar vendor, the adapter creates a neutral role-play quote from the transparent synthetic fixture template and rebinds it to the current context:

- a quote ID derived from the current call ID;
- evidence IDs derived from the current call ID and evidence position;
- the current job ID and locked JobSpec version;
- the discovered vendor record and Tavily provenance;
- `data_classification=role_play` on the vendor, quote, and transcript evidence;
- a synthetic `recordings.example.com` URL derived from the call ID;
- transcript excerpt and claim text that say the scenario is role play and not a claim about the company;
- neutral synthetic fee descriptions, totals, binding status, and availability inherited from the transparent template;
- an explicit role-play notice in verified metadata;
- no copied hidden-fee accusation, behavioral red flag, or company-specific concession.

The current three-vendor discovery order is preserved. A repeated call for an already persisted attempt remains idempotent through the existing attempt lookup.

### Failure recovery

`initiate_single_quote_call` already persists a pending `CallAttempt` before invoking a provider. It will treat any provider-boundary `DomainError` raised after that point as a failed attempt:

1. mark the attempt `failed` with a completion timestamp;
2. mark the job `failed`;
3. re-raise the original safe domain error.

The handler must not catch programming errors, validation bugs, or arbitrary exceptions. Those remain visible to tests and error monitoring. The existing `ProviderConfigurationError` and `ProviderRequestError` behavior is preserved.

## Data Flow

### Document intake

1. The API sends bounded synthetic text to OpenAI.
2. OpenAI returns strict structured JSON.
3. The parser validates the JobSpec independently.
4. The parser computes the authoritative missing-field list.
5. The full `DocumentParseResult` is validated.
6. Supabase persists the resulting unconfirmed job.

### Mock call batch with Tavily

1. Tavily returns normalized candidates with provenance.
2. Orchestration deduplicates candidates and selects the first three.
3. The job moves from `confirmed` to `calling`.
4. Each attempt persists the identical confirmed JobSpec snapshot before provider execution.
5. `MockVoiceProvider` generates an explicitly role-play result for each discovered vendor.
6. Canonical calls, quotes, transcript evidence, and synthetic recording URLs persist through Supabase.
7. After three canonical calls, the job moves to `quotes_ready`.

## API and Contract Compatibility

No route or public schema changes are required. The implementation changes how existing contracts are populated:

- `DocumentParseResult.missing_fields` is normalized to the canonical contract value.
- Quotes and evidence for discovered vendors use the existing `role_play` data-classification value.
- Existing fixture-vendor responses remain `synthetic` and byte-for-byte compatible apart from code paths shared for identifier rebinding.

OpenAPI export and generated frontend types are still checked by the repository gate even though no schema delta is expected.

## Error and Honesty Behavior

- OpenAI output cannot confirm or lock a JobSpec.
- Normalization computes metadata only; it never invents move facts.
- Tavily provenance remains attached to the vendor but is not quote evidence.
- Role-play quote evidence is synthetic and explicitly disclaims real-company behavior.
- No hidden-fee or negotiation claim from the fixture vendors is rebound to an unfamiliar discovered vendor.
- A synchronous provider-domain failure leaves a persisted failed attempt and failed job instead of a job stuck in `calling`.
- Enabled-provider errors do not fall back to a different provider.
- Secrets remain Render-managed and never enter source, logs, fixtures, tests, or generated artifacts.

## Testing

### OpenAI parser

- accepts a strict response whose model-supplied missing list is incomplete or differently ordered;
- returns `missing_fields == job_spec.missing_required_fields()`;
- preserves warnings, confirmation fields, and provenance;
- rejects a missing or invalid JobSpec;
- continues to reject confirmed, locked, or non-document output.

### Mock voice

- preserves current fixture-vendor quote behavior;
- accepts an unfamiliar `role_play` vendor with Tavily provenance;
- emits unique quote IDs, evidence IDs, provider IDs, and recording URLs per call;
- binds the current job, vendor, call, and JobSpec version;
- produces only role-play classified vendor, quote, and evidence data;
- includes the explicit non-claim notice;
- does not reuse fixture hidden-fee findings or vendor-specific red flags.

### Orchestration and persistence

- exactly three distinct discovered vendors receive calls;
- all attempts contain the same locked JobSpec snapshot;
- the batch reaches `quotes_ready` with three calls and three quotes;
- a provider `DomainError` after attempt creation marks the attempt and job failed;
- Supabase fake-transport tests cover arbitrary discovered-vendor persistence;
- the complete create/confirm/calls/negotiate/report loop remains idempotent.

### Gates and live smoke tests

- targeted backend tests pass;
- `python scripts/check.py` passes;
- `python -m evals.run` remains 14/14 or better;
- the branch is pushed and Render redeploys successfully;
- live Tavily discovery reports `source=tavily`;
- live OpenAI document intake returns HTTP 201 with canonical missing fields;
- Supabase reads back the created synthetic job;
- mock `/calls` reaches `quotes_ready` with exactly three role-play calls.

## Non-Goals

- Placing real phone calls to Tavily-discovered companies.
- Claiming that a discovered company supplied a quote, hid a fee, negotiated, or made a commitment.
- Changing ranking rules, fee categories, or negotiation leverage requirements.
- Completing the live ElevenLabs webhook-to-canonical-quote gap.
- Frontend feature work.
- Persisting raw provider responses or raw transcripts.

