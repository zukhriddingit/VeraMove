# Integration boundaries

Deterministic mock providers remain the default and are the only providers exercised by normal
development, demos, automated tests, and CI. Optional live voice stays behind the same orchestration
protocol and fails closed unless its explicit runtime settings are complete.

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
`JobSpecV1` used by voice intake. `OpenAIDocumentParser` accepts an injected structured-output client
and revalidates the response with Pydantic. `OpenAIRecommendationNarrator` can explain a
deterministic ranking but cannot change its order or findings. `NegotiationGateway` remains
compatible with the seeded mock. Deterministic implementations are wired in both mock and live
voice modes; no model call occurs in mock mode.

## Tavily

`VendorDiscoveryGateway` preserves the original origin/destination method and adds cached call-list
sourcing by city, state, service type, and radius. The mock returns the three committed fictional
vendors. The optional normalizer accepts an injected Tavily client and stores no direct contact
details. Mock mode performs no search request.

## Supabase/PostgreSQL

The SQL migration describes optional future persistence. `InMemoryRepository` implements the job,
call, and quote repository protocols at runtime. Supabase remains unwired, so mock mode needs neither
a Supabase client nor a local instance.

## Adapter rules

A live adapter must remain behind an injected protocol, require explicit non-mock mode and
enablement, protect credentials, redact personal data in logs, preserve idempotency, and include
contract and failure tests with no external request. It may never silently activate or change
mock-mode acceptance behavior.
