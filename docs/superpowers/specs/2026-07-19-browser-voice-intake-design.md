# Browser Voice Intake Design

**Date:** 2026-07-19  
**Status:** Approved for implementation planning  
**Scope:** Replace the scripted web voice-interview experience with a real microphone conversation
when live voice is available, while preserving credential-free Demo Mode.

## Goal

Let a user complete the VeraMove intake interview by speaking with the existing ElevenLabs Intake
Agent directly in the browser. The conversation must materialize the same unconfirmed `JobSpecV1`
used by document intake, display a live transcript, and advance to the existing confirmation screen.

The implementation must reuse the current intake-session, signed post-call webhook, and voice
materialization boundaries. It must not expose the ElevenLabs API key, create a second job model, or
confirm or lock the job automatically.

## Current State

`apps/web/src/components/veramove/VoiceIntakePanel.tsx` currently streams a fixed transcript and
loads a synthetic job through the Demo adapter. Live mode disables the start button and says voice
intake is still being connected.

The backend already provides the durable parts of the live workflow:

- `POST /api/intake/sessions` reserves an intake-session ID and job ID without creating an incomplete
  `JobRecord`;
- `GET /api/intake/sessions/{session_id}` returns safe session status and exposes `job_spec` only after
  completion;
- the ElevenLabs post-call webhook verifies the provider signature and correlation variables;
- the voice materializer creates one canonical, unconfirmed `JobSpecV1` with
  `intake_source=voice`; and
- Supabase stores the session and resulting job in live mode.

The missing piece is authenticated browser audio plus browser-to-session correlation.

## Decision

Use the official `@elevenlabs/react` SDK with WebRTC. VeraMove's backend will request a short-lived,
single-conversation token from ElevenLabs using the server-only API key. The frontend will use that
token for the media session and pass only the server-created correlation variables.

This is an intentional, narrowly scoped exception to the earlier frontend rule against direct
provider calls: the browser may establish an encrypted ElevenLabs WebRTC media connection using an
ephemeral token. It may not receive a provider API key, call ElevenLabs REST endpoints, select an
agent ID, override the agent prompt, or call any other provider directly.

The alternatives were rejected for this release:

- the ElevenLabs widget is faster to embed but is harder to style, correlate, and integrate into the
  existing intake state machine; and
- proxying real-time audio through FastAPI adds avoidable latency, streaming infrastructure, and
  operational risk.

## End-to-End Flow

1. The user selects Live Mode and presses **Start voice interview**.
2. The frontend explains that microphone audio is sent to the AI intake provider and requests
   microphone permission from the browser.
3. The frontend creates a VeraMove intake session with `POST /api/intake/sessions`.
4. The frontend requests a WebRTC credential from
   `POST /api/intake/sessions/{session_id}/voice-token`.
5. FastAPI verifies live voice is explicitly enabled, reserves one credential issuance on the
   intake session, requests a conversation token for the configured Intake Agent through an
   ElevenLabs integration adapter, and returns the token plus the three canonical correlation
   variables.
6. The frontend starts the ElevenLabs session with the token and dynamic variables. The agent prompt,
   voice, model, and data-collection schema remain controlled by the ElevenLabs dashboard and the
   versioned repository assets.
7. The SDK returns a provider conversation ID. The frontend immediately attaches it with
   `POST /api/intake/sessions/{session_id}/conversation`.
8. SDK callbacks render final user transcripts and agent responses in the existing live transcript
   panel. Tentative transcript fragments may update the current row but must not create duplicate
   turns.
9. When the interview ends, the panel enters **Processing your answers** and polls
   `GET /api/intake/sessions/{session_id}` with a bounded timeout.
10. ElevenLabs sends its signed post-call webhook. Existing materialization validates the agent ID,
    session ID, job ID, agent-config version, collected fields, and canonical `JobSpecV1` invariants.
11. When the session becomes `completed`, the frontend navigates to `/confirm/{job_id}`. The user must
    still review and explicitly confirm the spec before any vendor call.

## API Contract

FastAPI OpenAPI remains the source of truth. Add the following generated contract surfaces.

### Issue a browser voice credential

`POST /api/intake/sessions/{session_id}/voice-token`

Response:

```json
{
  "conversation_token": "ephemeral-provider-token",
  "dynamic_variables": {
    "job_id": "00000000-0000-0000-0000-000000000000",
    "intake_session_id": "00000000-0000-0000-0000-000000000000",
    "agent_config_version": "intake-v1"
  }
}
```

The real token must never appear in logs, fixtures, errors, analytics, or persisted storage. Tests use
an obvious synthetic value. The response must use `Cache-Control: no-store`.

The endpoint fails closed unless `APP_MODE=live`, `LIVE_CALLS_ENABLED=true`, Supabase is enabled, the
session is still pending and has not received a credential, and the browser-intake subset of the
reviewed ElevenLabs configuration is complete. That subset includes the API key, Intake Agent ID,
post-call webhook secret, and agent-config version; browser intake must not depend on outbound agent,
phone-number, or destination-number settings. Issuing a credential in mock mode is not allowed.

### Attach browser conversation correlation

`POST /api/intake/sessions/{session_id}/conversation`

Request:

```json
{
  "conversation_id": "conv_synthetic_example"
}
```

Response: the existing `IntakeSessionResponse`, now in `in_progress` state.

The route supplies the configured Intake Agent ID internally; clients cannot choose the expected
agent. Existing transition and identity rules make the operation idempotent and prevent changing a
previously attached conversation ID.

### Existing polling contract

No changes are required to `GET /api/intake/sessions/{session_id}`. The frontend relies on:

- `pending` while the credential is being issued;
- `in_progress` after the conversation ID is attached;
- `completed` only after the webhook atomically persists the `JobSpecV1`; and
- `failed` with a safe generic UI message.

After changes, run `python scripts/export_openapi.py` followed by
`npm --prefix apps/web run generate:api`. Frontend code must import the generated response and request
types rather than duplicate them.

## Backend Boundaries

Add a small ElevenLabs token adapter under `services/api/app/integrations/elevenlabs`. It receives an
agent ID from server configuration, calls the provider's conversation-token endpoint through an
injectable HTTP transport, validates a non-empty bounded token, and converts all provider or parsing
failures to the existing safe provider error type.

The FastAPI route coordinates existing `IntakeSessionService` operations and the token adapter. The
orchestration layer must not import or call an external SDK. Tests inject a fake adapter/transport and
perform no live network calls.

Add a nullable `browser_credential_issued_at` timestamp to the internal `IntakeSession` and Supabase
table. A service method reserves issuance while the session is pending and rejects repeated
reservation. If the provider request then fails, the service marks the session failed with a bounded
safe code; Retry creates a new intake session. The provider token itself is never stored.

Attaching the SDK-returned conversation ID performs the existing `pending -> in_progress`
transition. Post-call materialization remains the only path that creates the voice `JobRecord`.

## Frontend Design

Keep the current panel layout and visual design. Replace the Live Mode placeholder with these states:

- **Ready to connect** — consent copy and enabled start button;
- **Requesting microphone** — browser permission in progress;
- **Connecting to voice agent** — intake session and WebRTC setup;
- **Agent speaking** / **Listening** — driven by SDK mode callbacks;
- **Processing your answers** — conversation ended and session polling;
- **Interview complete** — brief success state before navigation; and
- **Interview failed** — safe explanation with Retry and Switch to Demo actions.

The live transcript uses SDK message callbacks and renders only conversational user/agent text. It
must ignore debug messages and must not log message bodies. A visible **End interview** control calls
the SDK's end-session method. Cleanup on unmount ends the session, releases microphone tracks, clears
poll timers, and prevents state updates after navigation.

The SDK should be wrapped in a focused hook or adapter under `apps/web/src/lib/voice`; presentation
components must continue to use the centralized VeraMove API client and may not call FastAPI with raw
`fetch`.

The extracted-field preview remains hidden for live voice until the completed `job_spec` arrives. It
must render actual generated contract data, never the fixed Rock Hill fixture.

## Demo and Live Behavior

`APP_MODE=mock` and frontend Demo Mode remain credential-free and deterministic. The existing scripted
transcript, variants, and synthetic job adapter stay available for offline judging and local checks.

Real browser voice is offered only in Live Mode. The public UI must label it **Live AI voice** and
continue to tell users to use fictional details for the supervised hackathon demonstration. It must
not collect a phone number, name, email, or other identity field. The agent's existing AI/recording
disclosure and confirmation readback remain mandatory.

If the live backend reports voice unavailable, the panel must fail before requesting microphone
permission and offer the scripted Demo Mode. There is no silent fallback from a failed real
conversation to a fabricated completed job.

## Security and Abuse Controls

- Keep `ELEVENLABS_API_KEY` and agent IDs server-side.
- Return only a short-lived conversation token and exact correlation variables.
- Mark token responses `Cache-Control: no-store` and never persist the token.
- Restrict CORS to the reviewed Lovable and local development origins.
- Enforce one credential issuance attempt per pending intake session through persisted reservation
  metadata; retries create a new session.
- Reject token issuance for completed, failed, or already-correlated sessions.
- Do not accept prompt, first-message, voice, agent, or model overrides from the browser.
- Do not store live transcript text in the frontend, application logs, intake-session record, or
  browser storage. ElevenLabs' signed webhook remains the only materialization input.
- Preserve the no-real-PII rule and synthetic-data labeling in the UI and agent prompt.

## Error Handling

- Microphone denied: remain on Intake with browser-specific guidance and Retry.
- Backend or provider unavailable: show a safe connection error and Switch to Demo.
- SDK disconnect before conversation attachment: end local media and leave the pending session
  abandoned; do not create a job.
- Conversation attached but webhook delayed: poll for at most 60 seconds, then show a delayed-processing
  state with Retry status check rather than starting a second conversation.
- Session `failed`: show the safe failure code mapping without provider internals.
- Component unmount/navigation: end the active media session and stop polling.
- Duplicate start clicks: disable Start while setup, conversation, or processing is active.

## Testing

### Backend

- token adapter request URL, headers, timeout, success parsing, malformed response, and safe provider
  errors;
- token route rejects mock mode, incomplete live configuration, unknown session, non-pending session,
  and repeated issuance;
- token response has `Cache-Control: no-store` and never serializes the API key or agent ID;
- conversation attachment succeeds once, is idempotent for the same ID, and rejects identity changes;
- existing signed webhook completes the browser-created session and produces one unconfirmed voice
  `JobSpecV1`;
- no credentials, transcripts, or real PII appear in repository state.

### Frontend

- Demo Mode retains the scripted deterministic experience without calling live endpoints;
- Live start requests permission, creates a session, obtains a token, starts the SDK, and attaches the
  returned conversation ID in order;
- transcript callbacks normalize final user and agent turns without duplicates;
- End interview stops the SDK and begins bounded polling;
- completed polling navigates to the existing confirmation route;
- denied permission, token failure, SDK failure, webhook timeout, and failed-session states offer safe
  recovery actions;
- unmount cleans up media and timers;
- no presentation component uses raw `fetch` and no handwritten domain model is added.

The required gate remains `python scripts/check.py`, including Ruff, pytest, OpenAPI export, generated
frontend types, TypeScript, Vitest, and the production Vite build. Add a mocked browser-media test;
perform one manual real-browser smoke test against Render and the configured ElevenLabs Intake Agent
after automated checks pass.

## Deployment and Dashboard Requirements

No new secret value is required if the existing Render live voice configuration is complete. Apply
the Supabase migration that adds the nullable credential-issuance timestamp before deploying the new
backend. The ElevenLabs Intake Agent must have authenticated client access enabled so VeraMove can
issue WebRTC tokens. Its post-call webhook, data-collection schema, recording settings, prompt
variables, and agent-config version must remain aligned with repository assets.

Deploy the backend contract first, then the frontend. Verify:

1. `/api/integrations/status` reports live voice ready without revealing configuration values;
2. the Lovable origin is present in `CORS_ALLOW_ORIGINS`;
3. a fictional browser interview reaches `completed` and opens Confirm;
4. the generated JobSpec is unconfirmed and cites voice as its intake source; and
5. Demo Mode still completes without provider credentials.

## Acceptance Criteria

- A judge can press Start, grant microphone permission, hear and speak with the Intake Agent, and see
  the conversation transcript in the existing VeraMove panel.
- Ending a complete interview creates exactly one canonical, unconfirmed voice `JobSpecV1` and opens
  the normal confirmation step.
- No API key or persistent provider credential reaches the browser.
- No browser code calls provider REST APIs or supplies agent behavior overrides.
- Mock/Demo Mode still passes all checks without ElevenLabs or Supabase.
- Existing document intake, outbound calls, negotiation, and report behavior are unchanged.

## Provider References

- [ElevenLabs React SDK](https://elevenlabs.io/docs/eleven-agents/libraries/react)
- [Get a WebRTC conversation token](https://elevenlabs.io/docs/api-reference/conversations/get-webrtc-token)
- [ElevenLabs agent authentication](https://elevenlabs.io/docs/eleven-agents/customization/authentication)
- [ElevenLabs dynamic variables](https://elevenlabs.io/docs/eleven-agents/customization/personalization/dynamic-variables)
