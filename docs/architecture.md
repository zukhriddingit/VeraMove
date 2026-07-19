# Architecture

VeraMove is a thin vertical-slice monorepo. FastAPI is the contract authority, React is a typed API
consumer, and deterministic mocks prove the complete workflow without external infrastructure.

## Data flow

1. Structured intake or additive `POST /api/intake/document` produces one unconfirmed `JobSpecV1`.
2. The application stores an `intake_complete` aggregate through `JobRepository`.
3. Confirmation timestamps and locks version 1.0 before any provider call.
4. The call orchestrator creates an internal `CallAttempt` containing the locked spec snapshot before
   asking `VoiceProvider` to initiate a call. Pending and in-progress provider state never weakens
   the canonical completed `CallRecord` contract.
5. Mock batch calling composes three invocations of the same single-call primitive. Every call and
   quote references the same confirmed version.
6. Negotiation chooses a verified quote from a different vendor as leverage against the target quote
   and accepts a result only when price or terms measurably improve.
7. The completed mock aggregate exposes an evidence-backed `RecommendationV1` report.
8. Signed provider webhooks update matched attempts and append safe provider-neutral events exposed
   by additive `GET /api/jobs/{job_id}/events`; raw transcripts are not event data.

## State machine

```text
draft -> intake_complete -> confirmed -> calling -> quotes_ready -> negotiating -> completed
                         \-> failed <- active processing states
```

An explicit transition map rejects skipped or repeated transitions with HTTP 409. `completed` and
`failed` are terminal.

## Boundaries

Routers translate HTTP to typed service calls. The orchestration service receives five core injected
boundaries: `VoiceProvider`, `IntelligenceProvider`, `JobRepository`, `CallRepository`, and
`QuoteRepository`. Discovery and webhook normalization also remain injected adapters rather than
provider calls inside orchestration.

`InMemoryRepository` implements the three persistence protocols over one synchronized store and
defensively reconstructs Pydantic data. `CallAttempt` owns pending/in-progress state and provider
identifiers; completed `CallRecord` and `QuoteV1` objects remain canonical contract data. Mocks load
committed synthetic fixtures. The optional live voice adapter is fail-closed behind explicit mode,
enablement, identifiers, secret, and destination settings. Moving-specific rules remain in
`configs/moving.yaml`.

## Contract flow

Pydantic models generate FastAPI OpenAPI. `scripts/export_openapi.py` writes the canonical JSON;
`openapi-typescript` generates the only frontend domain types. Contract changes must regenerate both
committed artifacts. Document intake and event polling are additive frozen routes; their route-local
request/event envelopes reuse canonical domain models instead of creating a parallel domain tree.

## Optional live providers

Runtime composition selects OpenAI, Tavily, and Supabase independently from voice mode. OpenAI can
extract the shared document contract and narrate only an already-constructed recommendation
summary. Tavily can source vendor identities and provenance but not quote evidence. Supabase can
replace the process-local repository after both migrations are applied; its call-attempt table is
separate from canonical completed calls, and replay reservations rely on database uniqueness.
Every optional provider is disabled by default and enabled misconfiguration fails closed.
