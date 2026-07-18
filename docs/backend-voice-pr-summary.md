# Backend orchestration and voice PR summary

## Summary

- Splits orchestration across five injected core boundaries: voice, intelligence, job repository,
  call repository, and quote repository.
- Composes the deterministic three-vendor batch from one single-call primitive while preserving the
  same confirmed `JobSpecV1` version on every call and quote.
- Adds a fail-closed ElevenLabs native Twilio outbound adapter for a deliberately controlled live
  test, with HTTP transport injection so tests never dial.
- Authenticates and normalizes signed ElevenLabs webhooks into safe, replay-protected job events
  without retaining arbitrary provider payloads or raw transcript content.
- Negotiates only with verified, same-job, same-version, different-vendor evidence and requires a
  measurable price or term improvement before completing the report.

## Routes

Frozen workflow surface:

- `GET /health`
- `POST /api/intake/document`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/confirm`
- `POST /api/jobs/{job_id}/calls`
- `POST /api/webhooks/elevenlabs`
- `POST /api/jobs/{job_id}/negotiate`
- `GET /api/jobs/{job_id}/report`
- `GET /api/jobs/{job_id}/events`

Retained compatibility routes:

- `POST /api/jobs` for structured `JobSpecV1` intake.
- `GET /api/vendors/discover` for deterministic synthetic vendor discovery.

## Safety controls

- `APP_MODE=mock` is the credential-free default for development, demos, tests, and CI.
- Live initiation requires three independent gates: `APP_MODE=live`,
  `LIVE_CALLS_ENABLED=true`, and complete ElevenLabs agent/phone/webhook configuration plus the
  externally supplied `LIVE_TEST_TO_NUMBER`.
- Tests inject a recording HTTP transport. No automated test, mock smoke, startup path, or CI job
  makes a real network request or places a call.
- The destination is not accepted from job input or committed fixtures. The runbook requires
  explicit destination-owner consent and a single, human-supervised invocation.
- Webhooks authenticate the exact raw body with HMAC-SHA256, reject missing/malformed/invalid or
  stale timestamps outside the five-minute window, and atomically reserve a replay key.
- Normalized events allowlist identifiers, timestamps, and statuses. Phone numbers, raw transcript
  bodies, secrets, and arbitrary provider payloads are not stored in events or written to logs.

## Test evidence

- Final repository pipeline: `python scripts/check.py` passed Ruff, all 153 pytest tests, OpenAPI
  export, TypeScript API generation, frontend typecheck, all 4 tests in 1 Vitest file, and the Vite
  production build.
- Focused backend coverage includes `test_service.py`, `test_voice_tools.py`,
  `test_live_voice.py`, `test_webhooks.py`, `test_api.py`, `test_openapi.py`, and
  `test_documentation.py`.
- Live request tests assert the exact native outbound endpoint and payload through an injected fake
  transport; they do not perform a network call.
- Webhook tests cover valid signatures, invalid and stale signatures, malformed payloads, replay,
  unknown statuses, unmatched attempts, and transcript exclusion.
- Lifecycle and safety tests cover idempotent confirmation/calls/negotiation, all required call
  outcomes, immutable version references, invalid transitions, fake-leverage rejection, measurable
  improvement, and evidence-backed reporting.
- Generated artifact verification: regenerating `packages/contracts/openapi.json` and
  `apps/web/src/api/schema.d.ts` left both files with zero working-tree diff.
- The backend suite emits one non-failing `StarletteDeprecationWarning` from FastAPI's test-client
  compatibility import; there are no failed or skipped checks.

## Contract impact

- FastAPI OpenAPI remains canonical. This PR adds document-intake, job-event, signed provider
  webhook, and runtime-health API schemas and the document-intake/events routes; it makes no
  canonical field change to `JobSpecV1`, `CallRecord`, `QuoteV1`, or `RecommendationV1`.
- `packages/contracts/openapi.json` and `apps/web/src/api/schema.d.ts` were regenerated with the API
  changes. The additive artifacts require review from the canonical-contract owner and frontend
  owner before merge.
- Internal `CallAttempt`, provider reference/result, normalized webhook, and job-event models do not
  replace or weaken the canonical completed-call contracts.

## Known limitations

- Runtime persistence is in-memory; process restarts lose jobs, attempts, replay keys, and events.
- The controlled live path intentionally places at most one opted-in test call and does not produce
  a live report. Provider post-call data advances an attempt/event but is not converted into a
  canonical quote by this slice.
- Live intelligence remains deterministic; no OpenAI model request is wired in this slice.
- Tavily vendor discovery also remains deterministic, and Supabase persistence remains unwired.
- There is no automatic booking, payment, production retry queue, or operator console.
- The post-call raw transcript is intentionally not persisted; only safe normalized status metadata
  is retained.
- There is no release tag in this branch. Code freeze, merge, tag, release, and any live call require
  separate team authorization.
