# VeraMove

VeraMove is a standalone, mock-first AI moving-services negotiator. **VeraMove Intake** and document
intake both produce one versioned job specification. After explicit confirmation, one **VeraMove
Outbound Negotiator** calls exactly three recipients with the same locked JobSpec, uses verified
evidence for one negotiation, and explains the final ranking with transcript and recording
references. The default path is synthetic role-play; the separately gated live path can use three
official-site contacts only after each recipient explicitly authorizes the AI call and recording.

This public repository is a minimal hackathon starter for parallel development—not a production
moving, calling, or booking product.

## Product summary

The seeded demo proves this loop:

1. Create a structured two-bedroom `JobSpecV1` from synthetic intake.
2. Confirm and lock version 1.0.
3. Create exactly three synthetic vendor calls with itemized or supported non-quote outcomes.
4. Use a verified competing quote in a follow-up negotiation.
5. Measure a lower price and deposit.
6. Rank vendors and link reasons to transcript evidence and synthetic recording URLs.

## Architecture

FastAPI owns the canonical Pydantic contracts and generated OpenAPI schema. A small orchestration
service depends on repository, voice, negotiation, and discovery protocols. `APP_MODE=mock` wires
an in-memory repository and deterministic fixtures, so no external SDK or account is needed.

The TanStack Start/React frontend has one API client and imports types generated from FastAPI OpenAPI.
Optional OpenAI, Tavily, and Supabase adapters are independently enabled and fail closed. Live voice
uses the two reviewed agent roles, asynchronous signed provider events, durable Supabase
materialization, and signed recording capabilities. No provider credential is required for the
complete mock workflow.

See [architecture details](docs/architecture.md), [API contract rules](docs/api-contract.md), and
[integration boundaries](docs/integration-boundaries.md).

## Team & roles

| Person | Owns |
| --- | --- |
| Prathmesh Bhosale | Backend orchestration, ElevenLabs voice/negotiation system |
| Zukhriuddin ([@zukhriddingit](https://github.com/zukhriddingit)) | Data & intelligence layer — schema, OpenAI parsing/comparison/recommendation, dataset |
| Toheeb ([@Olacode01](https://github.com/Olacode01)) | Frontend (`apps/web`) |
| Arsalan ([@ars2711](https://github.com/ars2711)) | Product narrative & submission — everything in `docs/submission/`, final sign-off on the Project Summary, videos, and portal copy |

Full ownership boundaries and the claim-verification workflow are in [`AGENTS.md`](AGENTS.md) and
[`CODEOWNERS`](CODEOWNERS). Submission materials — scripts, claim ledger, requirements mapping,
final checklist — live in [`docs/submission/`](docs/submission).

## Repository structure

```text
apps/web/                    TanStack Start + React + TypeScript workflow UI
services/api/                FastAPI app, contracts, mocks, and tests
agents/                      Intake and negotiator ownership boundaries
packages/contracts/          Generated OpenAPI contract
configs/moving.yaml          Moving-specific questions and rules
data/demo/                   Clearly synthetic fixtures
evals/                       Mock workflow evaluation cases
supabase/migrations/         Optional PostgreSQL schema
scripts/                     Bootstrap, dev, check, and contract export
docs/                        Architecture and contributor documentation
docs/submission/             Project Summary, video scripts, claim ledger, submission checklist
.github/                     CI and pull-request template
```

## Prerequisites

- Python 3.11 or newer
- Node.js 20.19 or newer with npm
- Git

No API credentials, Supabase project, telephony account, or local database is required.

## Five-minute local setup

```bash
git clone https://github.com/zukhriddingit/VeraMove.git vera-move-negotiator
cd vera-move-negotiator
python scripts/bootstrap.py
python scripts/dev.py
```

Open the frontend at `http://127.0.0.1:5173`, FastAPI documentation at
`http://127.0.0.1:8000/docs`, and health at `http://127.0.0.1:8000/health`.

Stop both development servers with Ctrl+C.

## Environment variables

Copy `.env.example` only if you want to override safe defaults.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_MODE` | `mock` | Selects credential-free `mock` or fail-closed `live` voice mode |
| `API_HOST` | `127.0.0.1` | Documented API bind host |
| `API_PORT` | `8000` | Documented API port |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Browser API base URL |
| `VITE_DEMO_MODE` | `false` | Explicitly selects the synthetic browser demo adapter when `true` |
| `CORS_ALLOW_ORIGINS` | Lovable production + local Vite origins | Comma-separated exact browser origins allowed to call the API |
| `LIVE_CALLS_ENABLED` | `false` | Independent switch required before a controlled live call |
| `REAL_VENDOR_CALLS_ENABLED` | `false` | Separate fail-closed switch for reviewed official-business recipients |
| `VENDOR_CONTACT_HASH_SECRET` | empty | Strong backend-only HMAC secret for destination matching and suppression |
| `VENDOR_CONSENT_MAX_AGE_DAYS` | `30` | Maximum age of a recipient authorization, from 1 through 365 days |
| `ELEVENLABS_API_KEY` | empty | Backend-only ElevenLabs credential |
| `ELEVENLABS_INTAKE_AGENT_ID` | empty | Reviewed VeraMove Intake agent identifier |
| `ELEVENLABS_OUTBOUND_AGENT_ID` | empty | One shared quote/negotiation agent identifier |
| `ELEVENLABS_PHONE_NUMBER_ID` | empty | Imported Twilio number identifier managed by ElevenLabs |
| `ELEVENLABS_WEBHOOK_SECRET` | empty | Strong signed post-call webhook secret |
| `ELEVENLABS_PRECALL_SECRET` | empty | Strong inbound conversation-initiation secret |
| `LIVE_TEST_TO_NUMBERS` | empty | Exactly three unique consenting E.164 role-play destinations |
| `PUBLIC_API_BASE_URL` | empty | Deployed HTTPS API origin used for webhook/recording URLs |
| `RECORDING_SIGNING_SECRET` | empty | Strong recording-capability signing secret |
| `VOICE_OPERATOR_SECRET` | empty | Strong repair/operator authorization secret |
| `AGENT_CONFIG_VERSION` | empty | Must match both committed reviewed agent assets |
| `OPENAI_ENABLED` | `false` | Enables strict document extraction and summary-only narration |
| `OPENAI_API_KEY` | empty | Backend-only OpenAI credential |
| `OPENAI_DOCUMENT_MODEL` | `gpt-5.6-luna` | Strict document extraction model |
| `OPENAI_RECOMMENDATION_MODEL` | `gpt-5.6-terra` | Grounded summary narrator model |
| `TAVILY_ENABLED` | `false` | Enables provenance-backed vendor discovery |
| `TAVILY_API_KEY` | empty | Backend-only Tavily credential |
| `SUPABASE_ENABLED` | `false` | Replaces process memory with persistent repositories |
| `SUPABASE_URL` | empty | Supabase project HTTPS origin |
| `SUPABASE_SECRET_KEY` | empty | Backend-only Supabase secret key; never expose to the browser |

Each optional provider is selected only by its own `*_ENABLED=true` switch. Enabled providers
require complete credentials and never fall back to synthetic results after a failure. ElevenLabs
values are read only by the controlled live voice path and are validated when a call is initiated;
startup itself never contacts a provider or dials. Never commit a populated `.env` file.

## Render demo deployment

The repository includes `render.yaml` for one demo API service. Render installs
`services/api/requirements.txt` and starts the API with:

```bash
uvicorn services.api.app.main:app --host 0.0.0.0 --port $PORT
```

The Blueprint keeps `APP_MODE=mock`, every optional provider switch, and
`LIVE_CALLS_ENABLED=false`. Set the exact production frontend origin in Render's
`CORS_ALLOW_ORIGINS`; public HTTP(S) origins may be documented in `.env.example`. Never place API
keys, auth tokens, webhook secrets, phone credentials, or Supabase secret keys in frontend files,
repository files, issues, recordings, chat, or deployment logs.

The frontend-specific `apps/web/.env.example` documents the public build-time variables:

```dotenv
VITE_API_BASE_URL=https://veramove-api-demo-zukhriddingit.onrender.com
VITE_DEMO_MODE=false
```

`VITE_*` values are compiled into browser assets and are public. They may contain the backend URL,
but never OpenAI, Tavily, Supabase, ElevenLabs, or Twilio credentials.

Activate the non-voice providers one at a time while `LIVE_CALLS_ENABLED=false`:

1. Run every file in `supabase/migrations/` in filename order, through
   `202607210007_resumable_intake_vendor_calls.sql`, in the Supabase SQL editor.
   Enter `SUPABASE_URL` and the backend-only `SUPABASE_SECRET_KEY`, set
   `SUPABASE_ENABLED=true`, and verify a synthetic job survives one Render redeploy.
2. Enter `TAVILY_API_KEY`, set `TAVILY_ENABLED=true`, and verify
   `/api/vendors/discover` returns `source: "tavily"` with Tavily provenance.
3. Enter `OPENAI_API_KEY`, set `OPENAI_ENABLED=true`, and verify a synthetic text intake produces
   an unconfirmed, schema-valid `JobSpecV1`.

Render redeploys after environment changes. If an enabled provider is missing configuration or
fails, VeraMove reports a safe error instead of silently switching back to mock data.

After deployment, configure the authenticated conversation-initiation endpoint at
`https://<service-host>/api/webhooks/elevenlabs/pre-call` and signed post-call transcription at
`https://<service-host>/api/webhooks/elevenlabs`. Deployed live voice requires Supabase after all
five migrations; it never falls back to process memory. Browser voice additionally requires
authenticated client access on the reviewed Intake agent. The browser receives only an ephemeral
conversation token; the ElevenLabs API key remains server-side.

## Mock mode

Mock mode is the default complete demo mode. With optional provider switches off, it uses
process-local memory and deterministic synthetic fixtures for calls, quotes, transcripts,
recordings, discovery, intelligence, and negotiation. `APP_MODE=live` selects the asynchronous
two-agent voice workflow; OpenAI and Tavily remain independent, while durable Supabase is mandatory
for deployed live calls. Live voice stays disabled without `LIVE_CALLS_ENABLED=true`, exactly three
destinations, and the complete reviewed configuration in `docs/backend-voice-runbook.md`.

## Commands

| Command | Result |
| --- | --- |
| `python scripts/bootstrap.py` | Creates `.venv`, installs dependencies, exports OpenAPI, and generates TypeScript API types |
| `python scripts/dev.py` | Runs FastAPI on 8000 and Vite on 5173, stopping both on Ctrl+C |
| `python scripts/check.py` | Runs Ruff, pytest, contract generation, typecheck, frontend tests, and production build |
| `python scripts/export_openapi.py` | Regenerates `packages/contracts/openapi.json` |
| `npm --prefix apps/web run generate:api` | Regenerates `apps/web/src/api/schema.d.ts` |
| `python -m evals.run` | Runs deterministic synthetic intelligence evaluations |
| `.venv/bin/python scripts/live_voice_preflight.py --check-only` | Performs read-only redacted live readiness checks; never calls |
| `.venv/bin/python scripts/live_voice_smoke.py --confirm-supervised-one-call` | Places one explicit slot-zero provider smoke without canonical job state |

## API routes

| Method | Route | Mock behavior |
| --- | --- | --- |
| GET | `/health` | Reports service and selected runtime mode |
| GET | `/api/integrations/status` | Reports safe provider enablement and aggregate OpenAI usage |
| POST | `/api/intake/document` | Creates an unconfirmed job; OpenAI extracts only when enabled |
| POST | `/api/intake/sessions` | Reserves a safe voice-intake session without creating an incomplete job |
| GET | `/api/intake/sessions/{session_id}` | Returns intake status and the unconfirmed JobSpec after completion |
| POST | `/api/intake/sessions/{session_id}/voice-token` | Atomically issues one ephemeral browser conversation credential |
| POST | `/api/intake/sessions/{session_id}/conversation` | Attaches the SDK conversation ID to its durable intake session |
| GET | `/api/intake/conversations/{conversation_id}` | Resolves a safe intake session by provider conversation |
| POST | `/api/intake/sessions/{session_id}/resume` | Starts a new voice session containing only structured partial facts |
| POST | `/api/intake/sessions/{session_id}/finish-manually` | Materializes an incomplete intake as an editable draft |
| POST | `/api/jobs` | Creates a job at `intake_complete` through the selected repository |
| GET | `/api/jobs/{job_id}` | Returns the typed job aggregate |
| GET | `/api/jobs/{job_id}/events` | Returns safe normalized provider events |
| POST | `/api/jobs/{job_id}/confirm` | Locks the JobSpec and advances to `confirmed` |
| POST | `/api/jobs/{job_id}/calls` | Creates three completed synthetic calls and quotes |
| GET | `/api/jobs/{job_id}/vendor-research` | Returns safe Tavily research, contact display data, plans, and readiness |
| POST | `/api/jobs/{job_id}/vendor-research/discover` | Finds route-relevant mover candidates through the configured boundary |
| PUT | `/api/jobs/{job_id}/vendor-research/shortlist` | Saves exactly three reviewed candidates |
| POST | `/api/jobs/{job_id}/vendor-research/analyze` | Extracts official-site claims and contact candidates |
| PUT | `/api/jobs/{job_id}/vendor-research/call-authorizations` | Saves exactly three consent records by server-issued contact ID |
| POST | `/api/jobs/{job_id}/negotiate` | Adds a measurably improved synthetic quote |
| GET | `/api/jobs/{job_id}/report` | Returns the evidence-backed final recommendation |
| POST | `/api/webhooks/elevenlabs` | Authenticates, normalizes, and deduplicates a signed webhook |
| POST | `/api/webhooks/elevenlabs/pre-call` | Authenticates inbound Intake conversation initialization |
| GET | `/api/calls/{call_id}/recording` | Verifies a signed capability and streams provider audio server-side |
| POST | `/api/calls/{call_id}/repair` | Reconciles one stored done/failed conversation with operator authorization |
| GET | `/api/vendors/discover` | Returns synthetic or Tavily-provenance vendor candidates |

Illegal state transitions return HTTP 409 with a domain error code. Unknown jobs return HTTP 404.

## Team branch conventions

Branch from `main`, keep work inside the ownership boundaries in `AGENTS.md` and `CODEOWNERS`, and
use names such as `toheeb/orchestration`, `zukhriuddin/data-layer`, `frontend/demo-ui`, or
`arsalan/submission`. Rebase or merge `main` before requesting review; do not rewrite another
member's subsystem to resolve a local preference. Contract changes require coordinated backend and
frontend generation described in `AGENTS.md`. `AGENTS.md` is the source of truth for who owns what,
including the product-narrative and submission ownership in `docs/submission/`.

## Known limitations

- Official-business calling remains supervised and fail-closed. It requires separate per-recipient
  AI/recording consent, a permitted local call window, no suppression, and an explicit final Start;
  website publication alone is never treated as consent.
- Tavily supplies vendor identity, official-site provenance, public business contacts, and
  unverified pricing/fee leads. Only the recorded call can turn a lead into quote evidence.
- Supabase persistence has no end-user authentication, multi-tenant authorization, or production
  operator policy layer.
- No payment or booking workflow is implemented.
- There is no production retry queue or operator console; signed webhook replay and an authorized
  repair path handle the demo recovery cases.
- VeraMove intentionally does not retain raw transcripts or audio bytes. Recording playback depends
  on the configured short, nonzero provider retention window.
- Mock calls and negotiation complete synchronously.
- Live-mode draft edits are review-only until the backend exposes a canonical draft-update route.

## Synthetic data

Every vendor, move, policy, quote, transcript excerpt, recording URL, and recommendation in
`data/demo` is fictional and labeled synthetic. Example-domain URLs are not recordings of real
calls. The repository contains no real phone number, home address, customer identity, or personal
moving record.

## Future VeraAI integration

VeraMove remains independent from VeraAI. `JobSpecV1.source_context` contains only nullable
`vera_user_id` and `vera_property_id` identifiers so a future integration can correlate records
without coupling this repository to VeraAI services or authentication.

## License

MIT. See [LICENSE](LICENSE).
