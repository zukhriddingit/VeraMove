# VeraMove

VeraMove is a standalone, mock-first AI moving-services negotiator. It turns voice or document
intake into one locked job specification, compares three vendors on identical facts, negotiates
with verified evidence, and explains its final ranking with transcript and recording references.

This public repository is a minimal hackathon starter for parallel development—not a production
moving, calling, or booking product.

## Product summary

The seeded demo proves this loop:

1. Create a structured two-bedroom `JobSpecV1` from synthetic intake.
2. Confirm and lock version 1.0.
3. Create three synthetic vendor calls with itemized outcomes.
4. Use a verified competing quote in a follow-up negotiation.
5. Measure a lower price and deposit.
6. Rank vendors and link reasons to transcript evidence and synthetic recording URLs.

## Architecture

FastAPI owns the canonical Pydantic contracts and generated OpenAPI schema. A small orchestration
service depends on repository, voice, negotiation, and discovery protocols. `APP_MODE=mock` wires
an in-memory repository and deterministic fixtures, so no external SDK or account is needed.

The Vite/React frontend has one API client and imports types generated from FastAPI OpenAPI.
Optional OpenAI, Tavily, and Supabase adapters are independently enabled and fail closed. No local
database or provider credential is required for the complete mock workflow.

See [architecture details](docs/architecture.md), [API contract rules](docs/api-contract.md), and
[integration boundaries](docs/integration-boundaries.md).

## Team & roles

| Person | Owns |
| --- | --- |
| Toheeb ([@Olacode01](https://github.com/Olacode01)) | Backend orchestration, ElevenLabs voice/negotiation system |
| Zukhriuddin ([@zukhriddingit](https://github.com/zukhriddingit)) | Data & intelligence layer — schema, OpenAI parsing/comparison/recommendation, dataset |
| Northeastern teammate | Frontend (`apps/web`) |
| Arsalan ([@ars2711](https://github.com/ars2711)) | Product narrative & submission — everything in `docs/submission/`, final sign-off on the Project Summary, videos, and portal copy |

Full ownership boundaries and the claim-verification workflow are in [`AGENTS.md`](AGENTS.md) and
[`CODEOWNERS`](CODEOWNERS). Submission materials — scripts, claim ledger, requirements mapping,
final checklist — live in [`docs/submission/`](docs/submission).

## Repository structure

```text
apps/web/                    Vite + React + TypeScript demo UI
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
| `CORS_ALLOW_ORIGINS` | local Vite origins | Comma-separated exact browser origins allowed to call the API |
| `LIVE_CALLS_ENABLED` | `false` | Independent switch required before a controlled live call |
| `ELEVENLABS_*` | empty | Live agent, phone-number, webhook, and API configuration |
| `LIVE_TEST_TO_NUMBER` | empty | Externally supplied, opted-in live test destination |
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
`LIVE_CALLS_ENABLED=false`. Enter secrets and the exact frontend origin for
`CORS_ALLOW_ORIGINS` only in Render's environment controls. Never place those values in
`render.yaml`, `.env.example`, repository files, issues, recordings, chat, or deployment logs.

Activate the non-voice providers one at a time while `LIVE_CALLS_ENABLED=false`:

1. Run `supabase/migrations/202607180001_initial_schema.sql` and then
   `supabase/migrations/202607190002_live_persistence_hardening.sql` in the Supabase SQL editor.
   Enter `SUPABASE_URL` and the backend-only `SUPABASE_SECRET_KEY`, set
   `SUPABASE_ENABLED=true`, and verify a synthetic job survives one Render redeploy.
2. Enter `TAVILY_API_KEY`, set `TAVILY_ENABLED=true`, and verify
   `/api/vendors/discover` returns `source: "tavily"` with Tavily provenance.
3. Enter `OPENAI_API_KEY`, set `OPENAI_ENABLED=true`, and verify a synthetic text intake produces
   an unconfirmed, schema-valid `JobSpecV1`.

Render redeploys after environment changes. If an enabled provider is missing configuration or
fails, VeraMove reports a safe error instead of silently switching back to mock data.

After deployment, use `https://<service-host>/api/webhooks/elevenlabs` as the ElevenLabs post-call
webhook URL and copy its generated HMAC secret directly into Render. The service must remain at one
Uvicorn worker while it uses the in-memory repository. Jobs and call attempts disappear on restart
unless the Supabase adapter is enabled after both migrations are applied.

## Mock mode

Mock mode is the default complete demo mode. With optional provider switches off, it uses
process-local memory and deterministic synthetic fixtures for calls, quotes, transcripts,
recordings, discovery, intelligence, and negotiation. `APP_MODE=live` selects only the controlled
one-call voice adapter; OpenAI, Tavily, and Supabase remain independent. Live voice stays disabled
without `LIVE_CALLS_ENABLED=true` and the complete reviewed configuration documented in
`docs/backend-voice-runbook.md`.

## Commands

| Command | Result |
| --- | --- |
| `python scripts/bootstrap.py` | Creates `.venv`, installs dependencies, exports OpenAPI, and generates TypeScript API types |
| `python scripts/dev.py` | Runs FastAPI on 8000 and Vite on 5173, stopping both on Ctrl+C |
| `python scripts/check.py` | Runs Ruff, pytest, contract generation, typecheck, frontend tests, and production build |
| `python scripts/export_openapi.py` | Regenerates `packages/contracts/openapi.json` |
| `npm --prefix apps/web run generate:api` | Regenerates `apps/web/src/api/schema.d.ts` |
| `python -m evals.run` | Runs deterministic synthetic intelligence evaluations |

## API routes

| Method | Route | Mock behavior |
| --- | --- | --- |
| GET | `/health` | Reports service and selected runtime mode |
| POST | `/api/intake/document` | Creates an unconfirmed job; OpenAI extracts only when enabled |
| POST | `/api/jobs` | Creates a job at `intake_complete` through the selected repository |
| GET | `/api/jobs/{job_id}` | Returns the typed job aggregate |
| GET | `/api/jobs/{job_id}/events` | Returns safe normalized provider events |
| POST | `/api/jobs/{job_id}/confirm` | Locks the JobSpec and advances to `confirmed` |
| POST | `/api/jobs/{job_id}/calls` | Creates three completed synthetic calls and quotes |
| POST | `/api/jobs/{job_id}/negotiate` | Adds a measurably improved synthetic quote |
| GET | `/api/jobs/{job_id}/report` | Returns the evidence-backed final recommendation |
| POST | `/api/webhooks/elevenlabs` | Authenticates, normalizes, and deduplicates a signed webhook |
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

- The controlled live adapter can initiate at most one opted-in test call; it does not convert live
  post-call data into a canonical quote or complete a live report.
- A signed live ElevenLabs post-call webhook is authenticated and can be persisted, but it still
  does not materialize a canonical quote or report.
- Tavily supplies vendor identity and provenance only; it does not supply verified quotes or direct
  phone contacts.
- Supabase persistence has no end-user authentication or authorization layer.
- No payment or booking workflow is implemented.
- Mock calls and negotiation complete synchronously.
- The frontend is a functional route scaffold, not a polished production interface.
- In-memory data is single-process and resets on restart.

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
