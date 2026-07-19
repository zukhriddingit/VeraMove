# Render Demo Deployment Design

## Objective

Deploy the integrated VeraMove FastAPI backend to one public Render web service so the frontend can
use a stable HTTPS API URL and ElevenLabs can deliver signed post-call webhooks. Preserve the
credential-free mock default and do not commit secrets or personal data.

## Scope

This deployment covers the current integration branch, production startup configuration,
environment-backed CORS, Render service configuration, secret entry through the Render dashboard,
and public smoke tests. It does not add persistent storage, parse full live transcripts into
canonical quotes, or deploy the incoming frontend.

## Architecture

Render will build the repository with Python 3.13, install
`services/api/requirements.txt`, and start one Uvicorn worker bound to Render's `PORT`. Render
terminates TLS and exposes the application at an `onrender.com` URL. The existing in-memory
repository remains the only runtime store, so jobs survive normal requests but are lost whenever
the service restarts or redeploys.

The checked-in deployment configuration keeps mock mode and live calls disabled by default. The
demo operator explicitly enables live mode in Render and enters all ElevenLabs values in Render's
environment-variable UI. No populated `.env` file, API key, webhook secret, phone number, or real
call payload enters Git.

## Configuration

Add a comma-separated `CORS_ALLOW_ORIGINS` setting. When absent, the application continues to allow
only `http://127.0.0.1:5173` and `http://localhost:5173`. In deployment, the variable will contain
only the exact public frontend origin once Member 3 supplies it. Wildcard origins are not used.

The Render service uses these non-secret values:

- runtime: Python
- Python line: 3.13
- build command: `pip install -r services/api/requirements.txt`
- start command: `uvicorn services.api.app.main:app --host 0.0.0.0 --port $PORT`
- health check: `/health`
- safe defaults: `APP_MODE=mock`, `LIVE_CALLS_ENABLED=false`

The Render dashboard, not the repository, owns the live values:

- `APP_MODE=live`
- `LIVE_CALLS_ENABLED=true`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_QUOTE_AGENT_ID`
- `ELEVENLABS_NEGOTIATOR_AGENT_ID`
- `ELEVENLABS_PHONE_NUMBER_ID`
- `ELEVENLABS_WEBHOOK_SECRET`
- `LIVE_TEST_TO_NUMBER`
- `CORS_ALLOW_ORIGINS` after the frontend URL is known

## Request and Webhook Flow

1. The frontend sends typed API requests to the Render HTTPS origin.
2. VeraMove creates and confirms a synthetic job in the single process's memory.
3. A controlled call request sends the locked JobSpec to ElevenLabs through the existing live
   adapter.
4. ElevenLabs posts a signed callback to
   `https://<render-service>/api/webhooks/elevenlabs`.
5. VeraMove validates the raw-body HMAC and timestamp, deduplicates the event, matches it by
   conversation ID, updates the attempt, and exposes safe metadata through the job events endpoint.

The webhook returns a successful response only after authentication and normalization. Invalid
signatures remain `401`, malformed signed payloads remain `400`, and replayed events are acknowledged
without duplicate state.

## Testing and Acceptance

Before deployment:

- unit-test environment parsing and CORS defaults/overrides;
- run the existing live-voice and webhook suites;
- run `python scripts/check.py`.

After deployment:

- `GET /health` returns HTTP 200 with the expected mode;
- `GET /docs` loads the public OpenAPI UI;
- a synthetic create/confirm/read cycle succeeds;
- the configured frontend origin passes a CORS preflight;
- one controlled outbound call succeeds only after explicit live enablement;
- one real signed ElevenLabs post-call webhook is accepted exactly once;
- the corresponding safe event is visible at `GET /api/jobs/{job_id}/events`.

## Limitations and Follow-up

The deployment is demo-grade rather than production-grade. In-memory data disappears on restart,
one process is required for consistent state, and live post-call transcripts are not yet converted
into canonical `CallRecord` and `QuoteV1` objects. Supabase persistence and evidence extraction are
separate follow-up work. Tavily is a required VeraMove integration and may be enabled after the
deployment is stable; Emdash and Wozcode are optional development tools and are not runtime
dependencies.
