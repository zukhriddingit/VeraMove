# Architecture

VeraMove is a mock-first vertical-slice monorepo. FastAPI is the contract authority, React is a typed
API consumer, and deterministic mocks prove the complete workflow without external infrastructure.
The live demonstration adds two professional voice roles without creating a second domain model.

## Canonical workflow

1. Document intake or **VeraMove Intake** produces the same unconfirmed `JobSpecV1`.
2. Explicit confirmation timestamps it and locks version `1.0` before any vendor call.
3. The call orchestrator creates exactly three initial attempts from a fixed fictional role-play
   roster. Stable destination slots 0–2 all receive the same locked JobSpec snapshot and hash.
4. One **VeraMove Outbound Negotiator** handles every outbound call. `call_mode=quote` selects the
   initial-quote branch; `call_mode=negotiation` selects the evidence-gated follow-up branch.
5. Signed post-call events are authenticated over raw bytes, normalized, cross-checked against the
   stored attempt, and atomically materialized into supported call outcomes.
6. At least two verified, same-version quotes are required before negotiation. The backend—not the
   agent—selects competing evidence and accepts only a measurable improvement.
7. The canonical report ranks eligible quotes and cites bounded transcript evidence plus signed
   VeraMove recording URLs.

The live path is asynchronous: provider initiation returns references, while signed completion
events create canonical outcomes. Mock mode completes the same conceptual flow synchronously.

## State and durable correlation

```text
draft -> intake_complete -> confirmed -> calling -> quotes_ready -> negotiating -> completed
                         \-> failed <- active processing states
```

`IntakeSession` exists before a voice-created job. `CallAttempt` exists before a completed
`CallRecord` and stores only safe correlation: kind, destination slot, expected role/config, locked
version/hash, provider references, and negotiation context. It never stores destination phone values.

Webhook receipts use leased compare-and-set semantics. Supabase finalization writes safe canonical
rows, advances the aggregate revision, and marks the receipt processed in one transaction. Replays,
out-of-order completion, and repair cannot create duplicate calls or lose concurrent results.

## Boundaries

Routers translate HTTP into typed service calls. Orchestration receives injected provider,
intelligence, discovery, verification, recording, and repository protocols; it does not call vendor
SDKs directly. Provider-shaped webhook objects stay internal and transient.

`InMemoryRepository` supports credential-free mock work. Deployed live voice requires the durable
Supabase implementation. Tavily remains a discovery-only boundary and never supplies the call roster,
phone contacts, quotes, or evidence. OpenAI can extract document intake and narrate an already-built
recommendation but cannot change canonical rankings or voice-supported facts.

## Trust and evidence

The imported Twilio number is managed by ElevenLabs. VeraMove supplies exactly three secret,
consenting destinations by slot; no destination is accepted from a job or Tavily result. The two
agents disclose AI/recording use, stop without consent, use fictional facts, and never book or pay.

Provider Data Collection is untrusted transport input. VeraMove validates primitive values and
bounded JSON strings, requires timestamped transcript support for material quote claims, and drops
phones, rationales, summaries, tool metadata, full transcripts, and raw bodies. Failed/non-quote
calls may lack audio; an itemized verified quote requires a canonical recording capability and
matching evidence.

## Recording and repair

Audio is not persisted by VeraMove. A signed capability URL identifies one stored call/job pair; the
backend fetches the corresponding provider conversation audio and streams only approved MIME types
with no-store headers. Provider credentials and upstream URLs never reach the browser. Audio Saving
and short nonzero retention are mandatory preflight checks.

An operator-authorized repair path fetches only a stored conversation. It reuses the normal
materializer for `done` analysis or a provider `failed` status and never redials an accepted call.

## Contract flow

Pydantic models generate FastAPI OpenAPI. `scripts/export_openapi.py` writes the canonical schema;
`openapi-typescript` generates the frontend types. Public contract changes must update backend tests,
OpenAPI, generated frontend types, and typed call sites together. No handwritten parallel JobSpec,
call, quote, or report models are permitted.

## Safe modes

`APP_MODE=mock` is the default and requires no credentials or Supabase. Live voice additionally
requires `APP_MODE=live`, `LIVE_CALLS_ENABLED=true`, durable Supabase, both agent IDs, the imported
number ID, strong signing/operator secrets, an HTTPS public origin, a reviewed config version, and
exactly three unique E.164 destinations. The preflight verifies provider credits, limits, agent
identity, Audio Saving, retention, Supabase, and public webhook reachability before a supervised run.
