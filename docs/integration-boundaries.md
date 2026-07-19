# Integration boundaries

Deterministic mock providers remain the default and are the only providers exercised by automated
tests and CI. OpenAI, Tavily, Supabase, and live voice each have an independent enablement switch,
stay behind injected protocols, and fail closed when their explicit settings are incomplete.

## ElevenLabs and Twilio

`VoiceProvider` is the provider-neutral call boundary. The mock provider completes synthetic quote
and negotiation calls deterministically. The optional live adapter sends one HTTP request through
HTTPX to ElevenLabs' native Twilio outbound endpoint and records provider conversation/call
identifiers in an internal `CallAttempt`. It requires `APP_MODE=live`, explicit live-call enablement,
all required ElevenLabs configuration, and one externally supplied test destination.

VeraMove sends the imported ElevenLabs phone-number identifier with the request. Twilio account
credentials are managed during the number import and are not sent by VeraMove to the outbound
endpoint.

The webhook adapter authenticates the exact raw body with a timestamped HMAC before parsing,
normalizes only allowlisted provider identifiers/status, and atomically rejects replays. Raw
transcripts, phone numbers, and arbitrary provider payloads are not retained in job events.

## OpenAI

`IntelligenceProvider` isolates the orchestration-facing document-intake and negotiation-planning
operations. `DocumentIntakeGateway` returns a strict `DocumentParseResult` containing the same
`JobSpecV1` used by voice intake. With `OPENAI_ENABLED=true`, the Responses API adapter requests a
strict `DocumentParseResult`, and `OpenAIDocumentParser` revalidates it with Pydantic before the job
is stored. `OpenAIRecommendationNarrator` receives only canonical rankings and findings; its output
can replace the summary but cannot change winners, totals, evidence, or order. Negotiation planning
remains deterministic. With the switch off, no model request occurs.

## Tavily

`VendorDiscoveryGateway` preserves the original origin/destination method and adds cached call-list
sourcing by city, state, service type, and radius. The mock returns the three committed fictional
vendors. The optional normalizer accepts an injected Tavily client and stores no direct contact
details. With `TAVILY_ENABLED=true`, the bounded search sends no raw-content, answer, or image
request and retains only result titles, URLs, and provenance. Provider failure never falls back to
mock candidates. With the switch off, no search request occurs.

## Supabase/PostgreSQL

`InMemoryRepository` remains the default implementation of the job, call, and quote protocols.
After both migrations are applied, `SUPABASE_ENABLED=true` selects a server-only PostgREST client
and `SupabaseRepository`. It persists jobs, attempts, canonical calls, quotes, evidence,
recommendations, and idempotent safe events. The secret key is sent only from the backend; enabled
failures never fall back to process memory.

## Adapter rules

A live adapter must remain behind an injected protocol, require explicit enablement, protect
credentials, redact personal data in logs, preserve idempotency, and include contract and failure
tests with no external request. Live voice additionally requires `APP_MODE=live`. No adapter may
silently activate or change credential-free mock acceptance behavior.
