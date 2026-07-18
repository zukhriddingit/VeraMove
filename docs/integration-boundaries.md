# Integration boundaries

All integrations are interfaces plus deterministic mock adapters. No production SDK is installed or
called.

## ElevenLabs and Twilio

`VoiceVendorGateway` is the future boundary for ElevenLabs conversation behavior and Twilio call
transport. The current adapter constructs three synthetic completed call records. The webhook route
accepts typed mock events and deduplicates their idempotency keys in memory.

## OpenAI

`NegotiationGateway` receives a locked JobSpec, all structured quotes, and one verified competitor.
The mock loads a fixed improved quote and records the competing quote ID. It performs no model call.

## Tavily

`VendorDiscoveryGateway` accepts origin and destination context. The mock ignores those strings and
returns the three committed fictional vendors. It performs no search request.

## Supabase/PostgreSQL

The SQL migration describes optional future persistence. `InMemoryJobRepository` is the only runtime
implementation. No Supabase client package or local instance is required.

## Future adapter rules

A real adapter must remain behind the existing protocol, require an explicit non-mock mode, protect
credentials, redact personal data in logs, preserve idempotency, and add contract plus failure tests.
It must not change mock-mode acceptance behavior.
