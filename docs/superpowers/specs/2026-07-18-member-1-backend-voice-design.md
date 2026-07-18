# Member 1 Backend and Voice Design

**Date:** 2026-07-18

**Branch:** `feat/member-1-backend-voice`

**Owner:** Toheeb (`@Olacode01`)

**Status:** Approved for implementation planning

## Purpose

This design defines Member 1's backend orchestration, ElevenLabs voice, telephony, webhook, negotiation, repository, and release-hygiene work for VeraMove. It builds on the existing repository and frozen shared contracts. It does not replace the starter architecture or take ownership of the frontend, canonical domain models, OpenAI implementation, Supabase implementation, or submission narrative.

The completed work must prove the full mock workflow and provide one deliberately gated live outbound-call path. Automated tests, normal local development, and CI must remain mock-only and must never place a real call.

## Current Baseline and First Repair

The feature branch starts from `main` commit `7bbd44b`. The ownership rewrite already assigns backend orchestration and voice files to Toheeb in `AGENTS.md` and `CODEOWNERS`, so those correct files will not be rewritten.

The updated baseline has one known failure: `test_documentation.py` still requires literal `Member 1` through `Member 4` headings even though `AGENTS.md` now uses real contributor names and roles. `CONTRIBUTING.md` also retains generic ownership wording. The first implementation commit will update only the stale assertion and generic contributor guidance, then verify the baseline:

`chore(repo): align ownership with final team plan`

## Chosen Integration Approach

Use ElevenLabs' native Twilio outbound-call API behind a small dependency-injected HTTP adapter. The adapter accepts provider-neutral call requests and returns provider identifiers such as `conversation_id` and `callSid`. This is preferred to adding both vendor SDKs because it keeps the dependency surface and test fixtures small while following the current native integration path documented by ElevenLabs.

The alternatives considered were:

1. ElevenLabs and Twilio SDK adapters. This reduces hand-written request code but increases dependencies and exposes the application to more SDK version churn.
2. A Twilio-first media-stream or registered-call implementation. This provides more transport control but introduces WebSocket and call-routing infrastructure that is unnecessary for the hackathon workflow.

The native HTTP adapter will use an injected transport, short timeouts, typed response parsing, and sanitized errors. Tests will substitute a recording fake transport and will not perform network requests.

## Ownership and Contract Boundaries

Member 1 owns API route orchestration, provider protocols, the ElevenLabs adapter, repositories used by orchestration, voice-agent assets, and voice-related tests. Existing canonical Pydantic contracts remain authoritative and owned by Member 2.

Additive endpoint request or event-envelope models that exist only to drive owned routes will live next to the API or orchestration layer. They will reuse `JobSpecV1`, `CallRecord`, `CallOutcome`, `QuoteV1`, and `RecommendationV1` instead of defining parallel domain objects. If a canonical model change becomes unavoidable, implementation stops at that boundary until the contract owner coordinates it.

FastAPI remains the OpenAPI authority. Additive routes and schemas will be exported through the existing generation scripts so the committed OpenAPI snapshot and frontend types do not drift.

## Service and Repository Architecture

The application service will depend on five explicit protocols:

- `VoiceProvider`: initiate one quote call, one quote batch through repeated single calls, and one negotiation call.
- `IntelligenceProvider`: transform document intake into a structured draft and generate negotiation instructions or decisions without coupling orchestration to a specific model vendor.
- `JobRepository`: create, load, save, confirm, and enforce the active immutable job-spec version.
- `CallRepository`: create and update calls, store provider identifiers, and record normalized call outcomes.
- `QuoteRepository`: save provisional or verified quotes and retrieve eligible competing quotes for negotiation.

The in-memory implementation may share one synchronized backing store so aggregate reads remain simple, but orchestration will receive the three repository interfaces separately. This preserves a clean future boundary for Member 2's Supabase adapter without requiring a database in mock mode.

The existing Member 2 intelligence gateway will be wrapped by an `IntelligenceProvider` adapter. Member 1 will not rewrite the OpenAI integration.

## API Surface and Lifecycle

The implementation freezes and supports:

- `POST /api/intake/document`
- `POST /api/jobs/{job_id}/confirm`
- `POST /api/jobs/{job_id}/calls`
- `POST /api/webhooks/elevenlabs`
- `POST /api/jobs/{job_id}/negotiate`
- `GET /api/jobs/{job_id}/report`
- `GET /api/jobs/{job_id}/events`
- `GET /health`
- `GET /api/jobs/{job_id}`

The existing structured job-creation route may remain for compatibility. Document intake will use the intelligence boundary in live-capable mode and a deterministic fixture in mock mode. No uploaded document or extracted raw personal content will be retained beyond the minimum structured job representation needed by the workflow.

The lifecycle is:

1. Intake creates a draft or intake-complete job from structured output.
2. Confirmation freezes the current `JobSpecV1` version. Repeating the same confirmation is safe and returns the existing confirmed aggregate; mutation of a confirmed version remains a conflict.
3. A single quote call is the primitive operation. Batch calling invokes that primitive for each selected mock vendor and associates every call with the same confirmed job-spec version.
4. Call initiation stores a pending call before invoking the provider, then stores provider identifiers returned by the adapter. A provider failure becomes a typed failed outcome rather than losing the call attempt.
5. Valid webhooks advance call status and save normalized outcomes or provisional quotes. Replayed events return a successful acknowledgement without duplicate calls, outcomes, quotes, or events.
6. Negotiation loads one verified eligible competing quote, initiates or simulates the negotiation call, and saves the improved quote or documented non-price improvement.
7. The report is available after completion and ranks evidence-backed results. The events endpoint exposes provider-neutral lifecycle events for polling or future streaming.

Illegal transitions return typed domain conflicts. Missing jobs return not-found errors. Provider configuration and transport failures are mapped to stable service errors without leaking secrets or raw payloads.

## Voice Agents and Tools

The repository will contain owned intake and negotiator agent assets: a human-readable prompt, a machine-readable agent configuration, and tool schemas. Prompts will require truthful representation, explicit confirmation of uncertain facts, no invented competing offers, itemized fees, recording/consent awareness, and a callback outcome when a complete quote cannot be obtained.

The orchestration tool layer will implement:

- `save_quote`
- `save_call_outcome`
- `get_verified_competing_quote`
- `request_callback`
- optional `log_fee`

Tools validate job, call, vendor, and job-spec-version relationships before writing. A competing quote is eligible only when it is verified, belongs to the same job and confirmed version, is from a different vendor, and contains supporting evidence. Provisional, failed, cross-version, self-vendor, or fabricated leverage is rejected.

## Webhook Security, Normalization, and Events

The ElevenLabs route reads the raw request body and signature header. The provider adapter validates the timestamped HMAC signature before JSON normalization. Production/live mode rejects missing, malformed, stale, or invalid signatures. Mock tests may use a deterministic test secret and generate valid signatures.

Replay protection uses a stable provider event identifier when present and otherwise derives a deterministic key from the event type, conversation identifier, and provider timestamp. The repository reserves that key atomically before applying state changes. A duplicate produces the original successful acknowledgement.

Raw transcripts and phone numbers are not written to application logs. Normalized events contain only identifiers, timestamps, status, outcome type, and safe metadata required by the UI. Provider statuses are mapped to the existing `CallStatus` and `CallOutcomeType` values; unknown statuses remain observable without inventing a successful outcome.

## Mock and Controlled Live Modes

`APP_MODE=mock` remains the default. It uses deterministic document intake, vendors, call outcomes, quotes, transcripts, and negotiation results. The mock provider supports a single call first and builds batch behavior from the same method.

Live outbound calling is allowed only when all of these conditions hold:

- `APP_MODE=live`
- `LIVE_CALLS_ENABLED=true`
- the required ElevenLabs/Twilio integration configuration is present
- `LIVE_TEST_TO_NUMBER` is configured outside the repository

The destination number is not accepted from or committed to demo fixtures. Startup may construct the live adapter without dialing, but a call method fails closed if the explicit live-call switch or destination is absent. No test sets the live switch, and injected transports make it possible to verify request formation without network access.

## Configuration

`.env.example` will document names and safe defaults for the application mode, live-call switch, ElevenLabs API key, ElevenLabs agent identifiers, imported phone-number identifier, webhook secret, public webhook URL, Twilio identifiers when needed for account setup, and the opt-in test destination. It will contain no usable secrets or phone numbers.

Provider configuration is validated at the boundary where it is required. Mock startup does not require external credentials. Live call initiation reports all missing configuration fields together and never silently falls back to mock behavior.

## Testing Strategy

Backend tests will cover:

- ownership-document alignment and the full baseline check;
- legal lifecycle transitions and rejected illegal transitions;
- idempotent confirmation and confirmed-spec immutability;
- every call referencing the same confirmed job-spec version;
- single-call behavior and batch composition;
- itemized quote, callback commitment, documented decline, and failed outcomes;
- live request construction with an injected fake transport and disabled-by-default safety gates;
- webhook signature validation, normalization, replay protection, and unknown events;
- quote and outcome tool validation;
- rejection of provisional, cross-version, same-vendor, or unsupported leverage;
- negotiation with verified leverage and measurable price or term improvement;
- report and event retrieval;
- the complete deterministic mock flow.

Tests will assert externally visible behavior and repository state rather than private implementation details. Existing frontend tests and generated contract checks must continue to pass.

## Release and Documentation

Member 1 will add concise smoke-test and release-hygiene documentation in an owned backend/release document. Submission narrative files remain Member 4's responsibility, and README changes require joint review under the repository ownership rules.

The final verification sequence is the repository-standard `python scripts/check.py`, followed by a mock API smoke test and an optional manually authorized live-call smoke test. The live smoke test is never part of CI and will not be executed automatically. No final tag or release is created before team code freeze.

## Focused Commit Sequence

The intended implementation history is:

1. `chore(repo): align ownership with final team plan`
2. `refactor(api): split orchestration provider and repository boundaries`
3. `feat(voice): add intake and negotiator agent tools`
4. `feat(voice): add gated ElevenLabs outbound calling`
5. `feat(api): normalize idempotent ElevenLabs webhooks`
6. `feat(api): complete verified quote negotiation flow`
7. `test(api): cover voice lifecycle and safety invariants`
8. `docs(repo): add backend smoke and release runbook`

Commits may be combined when a test and implementation are inseparable, but unrelated ownership areas will not be swept into these commits.

## Acceptance Criteria

The Member 1 scope is complete when:

- the exact frozen routes are stable and typed;
- the mock intake-to-report workflow passes deterministically;
- single and batch calls share one primitive;
- every call and quote preserves the confirmed job-spec version;
- webhook validation and replay protection prevent duplicate writes;
- negotiation cannot use fake or unverified leverage;
- the controlled live adapter is fail-closed and testable without dialing;
- no secrets, real phone numbers, raw transcripts, or personal move data are committed;
- `python scripts/check.py` passes;
- smoke-test and release notes are ready for code freeze; and
- the pull-request summary lists routes, safety controls, tests, contract impact, and known limitations.

## External Protocol References

- ElevenLabs native Twilio outbound call: <https://elevenlabs.io/docs/api-reference/twilio/outbound-call/>
- ElevenLabs webhook signatures and events: <https://elevenlabs.io/docs/eleven-api/resources/webhooks>
- ElevenLabs webhook tools: <https://elevenlabs.io/docs/eleven-agents/customization/tools/webhook-tools>
- Twilio call states and callbacks: <https://www.twilio.com/docs/voice/api/call-resource>
