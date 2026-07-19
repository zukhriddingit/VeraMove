# VeraMove web

The web application uses the FastAPI-generated types in `src/api/schema.d.ts` and the single
centralized client in `src/api/client.ts`. Presentation components must not call `fetch` or provider
REST APIs directly.

## Local configuration

Copy `.env.example` only for public build-time values:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_DEMO_MODE=false
```

All `VITE_*` values are public. Never put ElevenLabs, OpenAI, Tavily, Supabase, or Twilio secrets in
the frontend.

## Voice intake

Demo Mode keeps the deterministic role-play transcript and needs no credentials. Live Mode checks
the backend capability, requests microphone permission, creates a durable intake session, receives
one short-lived ElevenLabs conversation token from FastAPI, and opens a WebRTC conversation through
`@elevenlabs/react`. The browser receives no ElevenLabs API key and cannot override the agent,
prompt, model, or voice.

When the conversation ends, the browser polls the canonical intake session. Navigation to review
occurs only after the signed ElevenLabs post-call webhook creates an unconfirmed `JobSpecV1` with
`intake_source=voice`.

Before a live deployment, apply every Supabase migration through
`202607190005_browser_voice_intake.sql`, deploy the backend, enable authenticated client access on
the reviewed Intake agent, and verify the signed webhook. Use fictional details and a consenting
speaker for the manual browser test.

## Checks

```bash
npm run generate:api
npm run typecheck
npm test
npm run build
```
