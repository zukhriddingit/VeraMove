# Backend orchestration and voice PR summary

## Summary

- Adds two agent roles: **VeraMove Intake** and one shared **VeraMove Outbound Negotiator**.
- Produces one canonical unconfirmed `JobSpecV1` from either document or voice intake, then requires
  explicit confirmation before vendor calling.
- Initiates exactly three initial role-play calls with the same locked JobSpec and stable secret
  destination slots. The shared outbound agent branches on `call_mode=quote` or
  `call_mode=negotiation`.
- Authenticates provider events, materializes all supported outcomes atomically in Supabase, requires
  per-claim evidence for verified quotes, and produces the canonical report after measurable
  negotiation improvement.
- Proxies provider recordings through signed VeraMove capabilities and supports idempotent,
  operator-authorized conversation repair without redialing.

## Routes

The FastAPI/OpenAPI surface includes document and structured intake, typed voice-intake sessions,
job confirmation/state, calls, negotiation, report, safe events, vendor discovery, authenticated
ElevenLabs pre-call and post-call webhooks, signed recording streaming, conversation repair, runtime
health, and safe OpenAI usage status. FastAPI OpenAPI remains canonical; generated frontend types are
committed with every public change.

## Safety controls

- `APP_MODE=mock` is credential-free and remains the default for development, tests, demo fallback,
  and CI.
- Full live mode requires `APP_MODE=live`, `LIVE_CALLS_ENABLED=true`, durable Supabase, exactly three
  unique E.164 destination secrets, both agent IDs, the imported phone-number ID, strong pre-call,
  post-call, recording, and operator secrets, an HTTPS public origin, and a reviewed agent config
  version.
- Three consenting teammates represent fictional vendors. Tavily identities and real moving-company
  phone contacts can never enter the live call roster.
- Raw webhook bytes are authenticated before parsing. Phones, arbitrary metadata, raw transcript
  bodies, analysis rationales, audio, and secrets are neither persisted nor logged.
- Provider claims become canonical only after stored identity/version/hash checks and per-claim
  transcript evidence. A recording URL is optional for non-quote failure/callback/decline outcomes,
  but mandatory for an evidence-backed itemized quote.
- Preflight is read-only and emits only booleans, counts, and redacted identifiers. The separate
  one-call smoke needs explicit operator confirmation, always uses slot zero, and creates no
  canonical batch state.

## Test evidence

- Contract tests cover mutually exclusive outcomes, terminal status consistency, optional non-quote
  recording, and quote/call/evidence identity.
- Agent drift tests verify exactly two reviewed roles, 24 intake and 14 outbound Data Collection
  fields, required disclosure/stop rules, and config version alignment.
- Fake transports cover three distinct slot payloads, one outbound ID, identical locked facts,
  provider errors, safe webhook parsing, audio proxy failure, and preflight/smoke refusal paths.
- Repository tests cover leased receipt concurrency, replay, out-of-order completion, atomic Supabase
  finalization, and idempotent repair.
- The required final evidence is a clean `python scripts/check.py`, deterministic mock workflow,
  agent-asset check, redacted preflight, one supervised synthetic smoke, and full supervised demo.
  Update this section with the final observed counts only after those gates run.

## Contract impact

FastAPI OpenAPI remains canonical. Public additions include voice-intake session/pre-call models,
recording and repair routes, integration status, and asynchronous live-state responses. Existing
domain validation is tightened: supported outcome details are mutually exclusive; a non-quote
recording URL is optional; verified quotes still require matching call/evidence recording identity.
Provider envelopes, `CallAttempt`, `IntakeSession`, and webhook leases remain internal and do not
create handwritten duplicate frontend contracts.

## Known limitations

- This is a supervised fictional-role-play demo, not a production calling, moving, or booking system.
- Supabase has no end-user authentication/authorization layer or production multi-tenant policy.
- There is no automatic booking, payment, production retry queue, or operator console.
- Full transcripts and audio are intentionally not retained by VeraMove; playback depends on the
  configured short provider retention window.
- Provider dashboard synchronization is manual and must be rechecked against committed assets before
  each live run.
- The frontend is a typed functional demo and may not expose every operator repair/status control.
- There is no release tag in this branch. No release tag before code freeze; merge, release, and any
  live call require separate team authorization.
