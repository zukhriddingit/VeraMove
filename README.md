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

The Vite/React frontend has one API client and imports types generated from FastAPI OpenAPI. The
optional Supabase migration stores versioned payloads as JSONB, but no local database is required.

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
git clone <repository-url> vera-move-negotiator
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
| `APP_MODE` | `mock` | Only supported runtime mode in this starter |
| `API_HOST` | `127.0.0.1` | Documented API bind host |
| `API_PORT` | `8000` | Documented API port |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Browser API base URL |

The remaining empty names in `.env.example` reserve future adapter configuration. The starter does
not read them or call those services. Never commit a populated `.env` file.

## Mock mode

Mock mode is the default and only implemented mode. It uses process-local memory, so jobs disappear
when the API restarts. Calls, quotes, transcripts, recordings, discovery results, and negotiation
results are deterministic synthetic fixtures. Setting `APP_MODE` to another value fails fast rather
than silently attempting a real integration.

## Commands

| Command | Result |
| --- | --- |
| `python scripts/bootstrap.py` | Creates `.venv`, installs dependencies, exports OpenAPI, and generates TypeScript API types |
| `python scripts/dev.py` | Runs FastAPI on 8000 and Vite on 5173, stopping both on Ctrl+C |
| `python scripts/check.py` | Runs Ruff, pytest, contract generation, typecheck, frontend tests, and production build |
| `python scripts/export_openapi.py` | Regenerates `packages/contracts/openapi.json` |
| `npm --prefix apps/web run generate:api` | Regenerates `apps/web/src/api/schema.d.ts` |

## API routes

| Method | Route | Mock behavior |
| --- | --- | --- |
| GET | `/health` | Reports service and mock mode |
| POST | `/api/jobs` | Creates an in-memory job at `intake_complete` |
| GET | `/api/jobs/{job_id}` | Returns the typed job aggregate |
| POST | `/api/jobs/{job_id}/confirm` | Locks the JobSpec and advances to `confirmed` |
| POST | `/api/jobs/{job_id}/calls` | Creates three completed synthetic calls and quotes |
| POST | `/api/jobs/{job_id}/negotiate` | Adds a measurably improved synthetic quote |
| GET | `/api/jobs/{job_id}/report` | Returns the evidence-backed final recommendation |
| POST | `/api/webhooks/elevenlabs` | Records an idempotent mock webhook event |
| GET | `/api/vendors/discover` | Returns three synthetic vendors |

Illegal state transitions return HTTP 409 with a domain error code. Unknown jobs return HTTP 404.

## Team branch conventions

Branch from `main`, keep work inside the ownership boundaries in `AGENTS.md` and `CODEOWNERS`, and
use names such as `toheeb/orchestration`, `zukhriuddin/data-layer`, `frontend/demo-ui`, or
`arsalan/submission`. Rebase or merge `main` before requesting review; do not rewrite another
member's subsystem to resolve a local preference. Contract changes require coordinated backend and
frontend generation described in `AGENTS.md`. `AGENTS.md` is the source of truth for who owns what,
including the product-narrative and submission ownership in `docs/submission/`.

## Known limitations

- No real voice interview, document parsing, outbound calls, model inference, or web search.
- No Supabase runtime adapter, persistence, authentication, authorization, payment, or booking.
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
