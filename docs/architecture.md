# Architecture

VeraMove is a thin vertical-slice monorepo. FastAPI is the contract authority, React is a typed API
consumer, and deterministic mocks prove the workflow without external infrastructure.

## Data flow

1. Intake submits a complete, unconfirmed `JobSpecV1`.
2. The application stores an `intake_complete` aggregate in `InMemoryJobRepository`.
3. Confirmation timestamps and locks version 1.0.
4. The call orchestrator passes the same locked spec to `VoiceVendorGateway` and receives three
   `CallRecord` objects with itemized `QuoteV1` outcomes.
5. The negotiation orchestrator selects the lowest verified competitor and passes it to
   `NegotiationGateway`.
6. The mock returns an improved quote with the competitor quote ID and transcript evidence.
7. The completed aggregate exposes an evidence-backed `RecommendationV1` report.

## State machine

```text
draft -> intake_complete -> confirmed -> calling -> quotes_ready -> negotiating -> completed
                         \-> failed <- active processing states
```

An explicit transition map rejects skipped or repeated transitions with HTTP 409. `completed` and
`failed` are terminal.

## Boundaries

Routers translate HTTP to typed service calls. The service depends on protocols. The in-memory
repository serializes and reconstructs Pydantic aggregates to prevent accidental alias mutation.
Mocks load committed synthetic fixtures and contain no SDK clients. Moving-specific rules remain in
`configs/moving.yaml`.

## Contract flow

Pydantic models generate FastAPI OpenAPI. `scripts/export_openapi.py` writes the canonical JSON;
`openapi-typescript` generates the only frontend domain types. Contract changes must regenerate both
committed artifacts.

## Optional persistence

The Supabase migration offers UUID, timestamp, foreign-key, index, JSONB, and webhook-idempotency
foundations. Runtime code intentionally does not import or connect to Supabase.
