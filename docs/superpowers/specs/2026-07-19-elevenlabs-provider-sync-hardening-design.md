# ElevenLabs Provider Sync Hardening Design

## Goal

Make the checked-in VeraMove voice-agent assets and read-only preflight accurately represent the
current ElevenLabs configuration model without adding provider writes, credentials, real participant
data, or unsupported tools.

## Scope

The patch is limited to agent manifests and prompts, deterministic asset generation, the manual
dashboard checklist, the read-only preflight, focused tests, and operator documentation. Core API
orchestration and repository code remains unchanged.

## Agent assets

The outbound prompt will reference every value required for quote and negotiation behavior using
ElevenLabs `{{dynamic_variable}}` syntax. Correlation-only values may remain outside the prompt but
will have explicit dashboard placeholders so they are defined and returned in post-call initiation
data. The agent manifests will distinguish VeraMove's review marker `2026-07-19.1` from the opaque
ElevenLabs `version_id` and `branch_id` captured after a provider save.

The current `tools.yaml` descriptions are conceptual backend boundaries, not deployable ElevenLabs
tools. Both agent manifests will therefore declare no provider tool IDs. The negotiator will continue
to rely on verified variables supplied before the call and durable post-call materialization.

## Deterministic provider mapping

`scripts/generate_agent_assets.py` will keep the reviewed list-shaped Data Collection documents and
add a pure transform that returns the ElevenLabs API shape: an object keyed by field identifier whose
values contain only `type` and `description`. This avoids duplicating complete provider payloads that
would require URLs, secret IDs, or provider resource IDs in source control.

## Dashboard and API configuration

The checklist will document the supported split explicitly:

- workspace conversation-initiation URL and secret-locator header;
- Intake-only webhook enablement with prompt override disabled;
- shared HMAC post-call webhook with retries, transcript and initiation-failure events, JSON format,
  and pushed audio disabled;
- imported Twilio number assigned to Intake for inbound calls while the same number is reused by the
  Outbound agent at call initiation;
- per-agent Audio Saving and an explicit one-to-seven-day retention choice;
- separate review of Twilio recording retention when outbound `call_recording_enabled` is used; and
- provider version descriptions plus captured opaque version and branch identifiers.

No example will contain a usable secret or participant identifier.

## Read-only preflight

The preflight will inspect the two configured agents, their current version metadata, workspace
settings, the configured phone number, and subscription capacity. It will reduce provider responses
to booleans and counts before reporting. Readiness will require:

- both expected agent identities and opaque provider version IDs;
- version descriptions matching `VeraMove 2026-07-19.1`;
- required outbound prompt placeholders;
- Intake-only conversation-initiation enablement;
- workspace pre-call HTTPS URL with a secret locator;
- a shared post-call webhook with transcript and initiation-failure events and pushed audio off;
- the configured phone number assigned to Intake for inbound calls; and
- existing Audio Saving, short retention, limits, and credit checks.

The preflight will never print raw provider IDs, URLs, secret IDs, headers, phone numbers, or API
payloads.

## Testing

Focused tests will prove the Data Collection transform, prompt placeholders, absence of provider
tools, checklist precision, read-only provider request sequence, redacted readiness output, and
fail-closed behavior when provider settings drift. Existing generator determinism and project asset
tests remain the primary regression boundary.
