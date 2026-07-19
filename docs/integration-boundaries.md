# Integration boundaries

Deterministic mock providers remain the default and are the only providers exercised by automated
tests and CI. OpenAI, Tavily, Supabase, and live voice each have an independent enablement switch,
stay behind injected protocols, and fail closed when their explicit settings are incomplete.

## ElevenLabs and Twilio

Exactly two ElevenLabs roles are configured: **VeraMove Intake** and **VeraMove Outbound
Negotiator**. Intake creates an unconfirmed voice JobSpec draft. One outbound agent uses
`call_mode=quote` and `call_mode=negotiation`; separate quote/negotiator agents are not allowed.

The live `VoiceProvider` sends exactly three initial requests to stable destination slots. All use
the same locked JobSpec, fictional roster, agent ID, and reviewed config version. Destination values
are secret deployment inputs belonging to three consenting role-play participants; they never enter
the domain contract, database, logs, fixtures, Tavily results, or responses. VeraMove sends the
imported ElevenLabs phone-number ID. Twilio credentials remain in provider controls.

The conversation-initiation endpoint authenticates its dedicated pre-call secret before using body
data. The post-call endpoint verifies the HMAC over exact raw bytes before JSON parsing. Only
allowlisted correlation, primitive collection values, and bounded transcript turns reach transient
processing. Raw bodies, phone metadata, rationales, summaries, and full transcripts are discarded.

Provider initiation and completion are separate. Once a provider reference exists, retry means
signed webhook replay or operator-authorized conversation repair, never another dial. No automated
test, preflight, startup path, or CI job calls a destination. The separate smoke script requires an
explicit operator flag and can invoke slot zero only without creating canonical job state.

Audio Saving and short nonzero provider retention are mandatory. VeraMove stores no audio bytes; a
signed call capability lets the backend stream stored provider audio while hiding the API key and
upstream URL.

## OpenAI

`IntelligenceProvider` isolates document extraction and deterministic negotiation planning.
`OpenAIDocumentParser` revalidates strict response data as the same `JobSpecV1` used by voice intake.
The recommendation narrator receives only canonical rankings and findings; it cannot reorder vendors,
change totals, invent evidence, or confirm a job. Safe usage telemetry retains capability, model,
token counts, latency, success category, and an optional request ID—never prompts, documents,
transcripts, model text, or credentials.

## Tavily

Tavily provides source-backed discovery and provenance only. It does not determine the three live
role-play vendors, supply direct phone contacts, generate quotes, verify transcript evidence, or
provide negotiating leverage. Provider failure never falls back to mock candidates when enabled.

## Supabase/PostgreSQL

`InMemoryRepository` supports mock mode. Deployed live voice requires `SUPABASE_ENABLED=true` after
all migrations. The server-only repository persists safe intake-session correlation, call attempts,
canonical calls/quotes/evidence/recommendations, aggregate revisions, and leased webhook receipts.
Its restricted RPC boundary atomically finalizes a provider event. It does not persist phone values,
raw webhooks, full transcripts, analysis envelopes, rationales, audio bytes, or secrets.

## Adapter rules

A live adapter must remain behind an injected protocol, require explicit enablement, use bounded
timeouts and inputs, redact sensitive data, preserve idempotency, and include fake-transport tests.
No adapter may silently activate, fall back after an enabled failure, or change credential-free mock
acceptance. Live voice additionally requires the redacted preflight and explicit human consent.
