# VeraMove Live Integrations Design

**Date:** 2026-07-19  
**Status:** Approved for implementation planning  
**Scope:** OpenAI document extraction, Tavily vendor discovery, and Supabase persistence. Frontend work is excluded.

## Goal

Add real, independently enabled OpenAI, Tavily, and Supabase adapters without weakening VeraMove's credential-free mock mode, deterministic evidence rules, or fail-closed live-call controls.

The three integrations are isolated slices. A missing or failing provider must not silently switch an enabled production workflow to synthetic data, and enabling one integration must not require enabling the other two.

## Constraints

- `APP_MODE=mock` remains the default and runs without credentials or Supabase.
- Existing API route paths remain stable.
- OpenAI may extract document facts and narrate a deterministic result, but it may not confirm a job, reorder deterministic rankings, verify unsupported facts, or fabricate negotiation evidence.
- Tavily supplies vendor candidates and provenance only. Search results are not quotes and are never treated as verified pricing evidence.
- Supabase is server-side persistence. No elevated Supabase key may enter frontend code, OpenAPI, logs, fixtures, or committed configuration.
- Provider failures are explicit. There is no automatic production fallback from an enabled live adapter to a mock adapter.
- Automated tests use injected fake transports and never make OpenAI, Tavily, Supabase, ElevenLabs, Twilio, or telephone calls.
- No real PII, phone numbers, addresses, transcripts, recordings, or customer moving records may be added to the repository.
- Tavily runtime wiring and Supabase repository wiring cross the backend owner's subsystem boundary. Those changes must be additive, isolated in focused commits, and reviewed by Toheeb.

## Configuration

Each adapter has an independent activation flag:

| Integration | Enablement | Required configuration | Safe default |
| --- | --- | --- | --- |
| OpenAI | `OPENAI_ENABLED=true` | `OPENAI_API_KEY` | disabled |
| Tavily | `TAVILY_ENABLED=true` | `TAVILY_API_KEY` | disabled |
| Supabase | `SUPABASE_ENABLED=true` | `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | disabled |

`SUPABASE_SECRET_KEY` is the preferred current server credential. The implementation also accepts the existing `SUPABASE_SERVICE_ROLE_KEY` as a documented legacy fallback, with the new secret-key variable taking precedence.

Provider-specific settings remain optional while their adapter is disabled:

- `OPENAI_DOCUMENT_MODEL` defaults to `gpt-5.6-luna` with explicit `reasoning.effort=none` and remains overrideable.
- `OPENAI_RECOMMENDATION_MODEL` defaults to `gpt-5.6-terra` with explicit `reasoning.effort=none` and remains overrideable for grounded narration.
- `OPENAI_API_BASE_URL`, `TAVILY_API_BASE_URL`, and `SUPABASE_URL` are validated HTTPS origins before use.

Enabled adapters validate required configuration before serving their first provider-dependent request. Configuration errors return the existing provider-configuration error shape without revealing values.

## Architecture

### Shared transport pattern

The adapters use injected synchronous JSON transports so unit tests can capture request method, URL, headers, and JSON without external traffic. Production transports use the existing `httpx` dependency with bounded timeouts. Error messages include provider, status class, and a safe summary, but never authorization headers, request bodies containing user data, or raw provider responses.

Provider modules remain behind existing protocols:

- OpenAI implements `StructuredDocumentClient` and `GroundedNarrativeClient`.
- Tavily implements `TavilySearchClient` and feeds `CachedTavilyVendorDiscovery`.
- Supabase implements `JobRepository`, `CallRepository`, and `QuoteRepository`.

Dependency composition selects adapters once from a `Settings` snapshot. Disabled integrations use the existing deterministic mock or in-memory implementation. Enabled integrations do not silently fall back after a request or persistence failure.

### OpenAI

The OpenAI adapter uses the Responses API with an explicit strict JSON schema derived from `DocumentParseResult`. The request supplies:

- a short outcome-first extraction prompt;
- the bounded `document_text` accepted by `POST /api/intake/document`;
- strict structured output;
- an explicitly configured model and reasoning effort appropriate for extraction.

The response parser accepts only the expected completed text output, decodes JSON, and revalidates it through `DocumentParseResult`. The existing `OpenAIDocumentParser` then enforces:

- `intake_source=document`;
- `confirmed=false`;
- `confirmed_at=null`;
- `locked_version=null`;
- exact agreement between `missing_fields` and `JobSpecV1.missing_required_fields()`.

Refusals, incomplete responses, empty output, invalid JSON, schema violations, authentication errors, timeouts, and rate limits become safe provider errors. The route never returns a partially trusted model payload.

OpenAI recommendation narration remains subordinate to deterministic recommendation construction. In live OpenAI mode, orchestration constructs and validates the recommendation first, then supplies only the locked `JobSpecV1`, immutable rankings, and findings to the narrator. Only the returned `summary` replaces the deterministic default summary; winners, totals, findings, evidence IDs, and recording URLs are copied unchanged from the deterministic result. Mock output remains unchanged.

### Tavily

The Tavily HTTP client calls `POST /search` with bearer authentication and a bounded request:

- `search_depth=basic`;
- `topic=general`;
- `max_results` limited by the existing gateway;
- `include_answer=false`;
- `include_raw_content=false`;
- `include_images=false`.

Only result title and URL are passed to `CachedTavilyVendorDiscovery`. The existing normalizer creates stable vendor IDs, marks provenance as Tavily, and intentionally omits direct contact details. Search snippets, generated answers, and raw page content are not persisted.

`GET /api/vendors/discover` uses the live gateway only when `TAVILY_ENABLED=true`. Its response source becomes a truthful closed value: `synthetic_mock` or `tavily`. Initial quote-batch orchestration also obtains candidates from the injected discovery gateway and requires exactly three distinct vendors before placing any call; mock discovery returns the existing three fixtures, while enabled Tavily discovery fails closed if fewer than three valid candidates remain after normalization. This is a public contract change, so Pydantic, backend tests, OpenAPI JSON, and generated TypeScript types must be updated together; no handwritten frontend model is added.

Tavily authentication errors, rate limits, malformed result envelopes, timeouts, and provider failures become safe provider errors. An enabled Tavily request never returns synthetic vendors as if they were search results.

### Supabase

The Supabase adapter uses the server-side Data API through an injected PostgREST JSON transport. This avoids adding a large SDK and keeps persistence testable without a project.

The existing migration remains the relational foundation. A follow-up migration must:

- enable Row Level Security on application tables;
- revoke direct `anon` and `authenticated` access;
- grant only the required server role privileges;
- preserve unique webhook idempotency keys and foreign keys;
- add `calls.record_type` with allowed values `attempt` and `canonical`, defaulting to `attempt`, so pending `CallAttempt` data and completed `CallRecord` data share an identity without an ambiguous payload.

The server secret key is sent only through backend `apikey` and authorization headers. It is never exposed through health responses or client configuration.

Repository behavior mirrors `InMemoryRepository`:

- jobs store the canonical `JobRecord` payload and indexed state/version columns;
- vendors are upserted before calls or quotes that reference them;
- call attempts are persisted before provider requests;
- canonical call completion updates the same call identity without losing provider references;
- quotes, transcript-evidence metadata, and recommendations are upserted with their canonical identifiers;
- normalized safe events are stored without raw transcript bodies or phone numbers;
- webhook reservation uses the database unique constraint as the atomic idempotency decision;
- confirmed `JobSpecV1` payloads remain immutable;
- verified competing quote lookup enforces different vendor, identical locked version, verified status, evidence, a clear total, and `manually_fabricated=false`.

Production `reset()` must fail closed rather than delete remote data. Test cleanup continues to use `InMemoryRepository` or a fake Supabase transport.

When Supabase is enabled, connectivity or write failures are surfaced. The service must not split a workflow across Supabase and process memory. When disabled, the existing in-memory repository remains unchanged.

## Data Flow

### Live document intake

1. Client sends bounded `document_text` to the existing intake route.
2. Orchestration selects the enabled OpenAI document gateway.
3. OpenAI returns a strict `DocumentParseResult` payload.
4. Pydantic and the parser enforce incomplete/unconfirmed safety rules.
5. The selected repository stores the resulting `JobRecord`.
6. The user must still explicitly confirm and lock the JobSpec before calls.

### Live vendor discovery

1. Client requests vendors with origin or destination context.
2. The enabled Tavily gateway builds a bounded moving-company query.
3. Tavily results are normalized to provenance-bearing `Vendor` records.
4. The gateway returns cached copies for identical queries.
5. Before any initial call, orchestration requires exactly three distinct candidates. Mock voice calls all three; controlled live voice still honors `initial_call_limit=1`. Every placed call snapshots the same locked JobSpec version.

### Persistent workflow

1. When Supabase is enabled, all repository operations use one Supabase repository instance.
2. Job confirmation, attempts, calls, quotes, events, and recommendations survive Render restarts.
3. Database uniqueness protects webhook idempotency across processes and restarts.
4. The API reconstructs the same `JobRecord` contract regardless of in-memory or Supabase persistence.

## API Compatibility

Route paths and primary job contracts remain unchanged. The only intended public schema change is:

```text
VendorDiscoveryResponse.source:
  "synthetic_mock" | "tavily"
```

The contract-change process is mandatory: update Pydantic and tests, export OpenAPI, regenerate TypeScript types, and run the full repository check. Generated frontend types are updated even though frontend feature work is excluded.

## Failure and Security Behavior

- Missing enablement flags keep live adapters inactive.
- An enabled adapter with missing configuration fails closed with a configuration error.
- Provider `401`/`403`, `429`, `5xx`, timeout, malformed JSON, and schema failures are mapped to safe errors.
- Secrets and authorization headers are never interpolated into exceptions or logs.
- OpenAI output is untrusted until strict Pydantic validation succeeds.
- Tavily data cannot become quote or leverage evidence.
- Supabase failures never trigger an automatic in-memory fallback.
- Supabase server credentials remain backend-only and Render-managed.
- Raw ElevenLabs transcripts remain excluded from ordinary event logs and this persistence slice.

## Testing

### Configuration

- all three integrations are disabled by default;
- valid truthy and falsey switches parse correctly;
- enabled adapters reject missing keys or invalid base URLs;
- no configuration error reveals a credential value.

### OpenAI

- request uses the configured model, strict schema, bounded text, and no unexpected tools;
- valid structured output returns the same `JobSpecV1` contract;
- confirmed or locked model output is rejected;
- refusal, incomplete output, invalid JSON, schema mismatch, `401`, `429`, `5xx`, and timeout paths fail safely;
- narration cannot mutate deterministic ranking data.

### Tavily

- request uses bearer auth and privacy-preserving search options;
- valid results normalize and cache with Tavily provenance;
- response source is `tavily` only for the live gateway;
- missing fields, malformed envelopes, `401`, `429`, `5xx`, and timeouts fail safely;
- enabled-provider failure never returns mock vendors.

### Supabase

- job create/get/save round trips exact Pydantic data;
- confirmed JobSpecs remain immutable;
- attempts persist before provider references and survive reconstruction;
- canonical calls, quotes, and recommendations upsert idempotently;
- webhook reservation is atomic and duplicate-safe;
- events exclude raw transcript content;
- verified competing quote selection enforces every safety predicate;
- transport errors do not fall back to memory;
- production reset is rejected.

### Repository gates

- targeted unit and API tests pass;
- `python scripts/check.py` passes;
- `python -m evals.run` remains 14/14 or better;
- mock create/confirm/calls/negotiate/report remains credential-free and deterministic;
- no automated test reaches a real provider.

## Deployment and Manual Validation

The code can be built and tested before credentials are supplied. After deployment, the user enters secrets directly into Render; they are never pasted into source or chat.

Recommended activation order:

1. Create a Supabase project, run committed migrations, enter `SUPABASE_URL` and `SUPABASE_SECRET_KEY`, enable Supabase, and verify a synthetic job survives one Render redeploy.
2. Enter `TAVILY_API_KEY`, enable Tavily, and verify one vendor-discovery response reports `source=tavily` with provenance URLs.
3. Enter `OPENAI_API_KEY`, enable OpenAI, and verify one synthetic document-text intake returns an unconfirmed, schema-valid JobSpec.
4. Keep `LIVE_CALLS_ENABLED=false` during these tests. Re-enable billable voice only for a separate controlled call.

`render.yaml` keeps all enablement flags false and marks credential fields `sync: false`. The public health response remains unchanged and does not expose integration flags, provider identifiers, service URLs, or credential-presence details.

## Explicit Non-Goals

- Frontend feature work.
- Automatically calling Tavily-discovered real businesses.
- Treating Tavily results as verified quotes.
- Allowing OpenAI to choose the winner or create evidence.
- Persisting raw phone numbers or raw transcript bodies.
- Supabase authentication for end users.
- Payments, booking, or production telephony compliance.
- Fixing the existing live ElevenLabs webhook-to-canonical-quote gap. That remains a backend/voice-owner follow-up; persistence will retain safe events but cannot invent a structured call outcome.

## Primary Documentation Consulted

- OpenAI current-model resolver output and official GPT-5.6 migration/prompting guides: `developers.openai.com`.
- Tavily Search API reference: `POST https://api.tavily.com/search`, bearer authentication, bounded search fields.
- Supabase Python/Data API and API-key guidance: server-side secret keys, least-privilege grants, RLS, and explicit Data API access.
