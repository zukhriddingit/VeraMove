# Integration boundaries

All integrations are interfaces plus deterministic mock adapters. No production SDK is installed or
called.

## ElevenLabs and Twilio

`VoiceVendorGateway` is the future boundary for ElevenLabs conversation behavior and Twilio call
transport. The current adapter constructs three synthetic completed call records. The webhook route
accepts typed mock events and deduplicates their idempotency keys in memory.

## OpenAI

`DocumentIntakeGateway` returns a strict `DocumentParseResult` containing the same `JobSpecV1` used
by voice intake. `OpenAIDocumentParser` accepts an injected structured-output client and revalidates
the response with Pydantic. `OpenAIRecommendationNarrator` can explain a deterministic ranking but
cannot change its order or findings. `NegotiationGateway` remains compatible with the seeded mock.
No provider is wired and no model call occurs in mock mode.

## Tavily

`VendorDiscoveryGateway` preserves the original origin/destination method and adds cached call-list
sourcing by city, state, service type, and radius. The mock returns the three committed fictional
vendors. The optional normalizer accepts an injected Tavily client and stores no direct contact
details. Mock mode performs no search request.

## Supabase/PostgreSQL

The SQL migration describes optional future persistence. `InMemoryJobRepository` is the only runtime
implementation. No Supabase client package or local instance is required.

## Future adapter rules

A real adapter must remain behind the existing protocol, require an explicit non-mock mode, protect
credentials, redact personal data in logs, preserve idempotency, and add contract plus failure tests.
It must not change mock-mode acceptance behavior.
