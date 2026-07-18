# VeraMove Hackathon Starter Design

**Date:** 2026-07-18  
**Repository:** `vera-move-negotiator`  
**Product:** VeraMove

## Purpose and Scope

This repository is a minimal, runnable starter for four developers building a standalone AI moving-services negotiator. It establishes the project structure, shared contracts, mock end-to-end workflow, development commands, ownership boundaries, documentation, and continuous integration. It does not implement production telephony, model calls, vendor discovery, authentication, payments, booking, or VeraAI integration.

The starter proves one synthetic MVP loop: create a move from structured intake data, confirm and lock its `JobSpecV1`, create three mock vendor calls and quotes, negotiate a measurable improvement using a verified competing quote, and return an evidence-backed ranked recommendation.

## Chosen Approach

Use a thin vertical-slice monorepo with FastAPI as the contract authority and deterministic mock implementations as the default runtime.

This approach is preferred over a deeply layered domain framework because the repository is a hackathon starter and must remain approachable. It is also preferred over a separately maintained OpenAPI or TypeScript contract because FastAPI's generated OpenAPI document is explicitly canonical.

## Repository and Runtime Architecture

The repository contains these independent areas:

- `services/api`: FastAPI application, Pydantic v2 models, state-machine rules, orchestration, repository interfaces, mock adapters, and backend tests.
- `apps/web`: Vite, React, TypeScript, Tailwind CSS, React Router, one shared API client, generated OpenAPI types, route placeholders, and frontend tests.
- `agents`: ownership-ready intake and negotiation prompt/agent boundaries without production model calls.
- `packages/contracts`: generated `openapi.json` and generated TypeScript API types. The generated artifacts are committed so a fresh clone has a visible contract snapshot.
- `configs`: moving-domain questions and rules in `moving.yaml`; vertical rules are not duplicated in application code.
- `data/demo`: clearly labeled synthetic vendors, policy cards, quotes, transcript evidence, move, and recommendation fixtures.
- `supabase/migrations`: an optional PostgreSQL schema using UUID keys and JSONB domain payloads. The application does not require Supabase in mock mode.
- `scripts`: cross-platform Python entry points for setup, development, validation, and OpenAPI export.
- `docs`, `evals`, and `.github`: architecture and integration documentation, starter evaluation cases, contributor guidance, ownership, and CI.

The Python package is importable from the repository root and from `services/api`. Backend dependencies remain in `services/api/requirements*.txt`; the frontend has its own minimal `package.json`. A root `package.json` is unnecessary.

## Domain Contracts

`services/api/app/contracts` defines versioned Pydantic models for:

- `JobSpecV1`
- `OriginDestinationAccess`
- `InventoryItem`
- `MovingServices`
- `Vendor`
- `FeeLineItem`
- `TranscriptEvidence`
- `QuoteV1`
- `CallRecord`
- `CallOutcome`
- `RecommendationV1`

`JobSpecV1` captures the required move dates, access details, dwelling and bedroom details, inventory, special items, requested services, insurance preference, confirmation state, and nullable `vera_user_id`/`vera_property_id` source identifiers. Confirmation creates a locked confirmed snapshot; later mutation attempts return a domain conflict.

`CallOutcome` uses a discriminating enum with exactly `itemized_quote`, `callback_commitment`, `documented_decline`, and `failed`. `QuoteV1` separates provisional and verified facts and records verification status, evidence references, and a recording URL.

Money uses decimal-safe values in Python and JSON numbers in the OpenAPI surface. Dates and timestamps use ISO 8601 values. Synthetic recording URLs use reserved example domains.

## Job State Machine

The job lifecycle is:

`draft -> intake_complete -> confirmed -> calling -> quotes_ready -> negotiating -> completed`

`failed` is reachable from active processing states. Only explicitly listed transitions are allowed. Attempts to confirm twice, call before confirmation, negotiate before quotes exist, or request a final report before completion produce a typed domain error. The API maps missing resources to HTTP 404, validation errors to HTTP 422, and state conflicts to HTTP 409 with a human-readable message and machine-readable error code.

For the minimal mock flow, job creation validates a complete request and stores the job at `intake_complete`; confirmation advances it to `confirmed`; starting calls advances through `calling` to `quotes_ready` synchronously; negotiation advances through `negotiating` to `completed` synchronously.

## API and Data Flow

FastAPI exposes:

- `GET /health`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/confirm`
- `POST /api/jobs/{job_id}/calls`
- `POST /api/jobs/{job_id}/negotiate`
- `GET /api/jobs/{job_id}/report`
- `POST /api/webhooks/elevenlabs`
- `GET /api/vendors/discover`

Routers depend on an application service. The service depends on repository and integration protocols, not concrete external SDKs. `APP_MODE=mock` wires an in-memory repository and deterministic ElevenLabs, OpenAI, and Tavily adapters. Twilio is represented at the voice boundary but never called.

The mock sequence is synchronous and deterministic:

1. A `JobSpecV1` is accepted and stored.
2. Confirmation timestamps and locks its current version.
3. The call orchestrator loads three synthetic vendors and creates three call records with itemized outcomes and evidence-linked initial quotes.
4. Negotiation selects the verified transparent competing quote and asks the premium vendor mock for an improved quote. The fixture guarantees a lower negotiated total or improved terms.
5. The report returns all vendors ranked with reasons, red flags, transcript evidence, and synthetic recording links.

The ElevenLabs webhook validates a typed mock event, supports an idempotency key, and records it without invoking external services. Vendor discovery returns synthetic Tavily results.

## Frontend Design

The frontend is deliberately functional rather than polished. It uses a Lovable-compatible Vite layout, React Router, and Tailwind CSS with no credential requirement.

Routes are:

- `/`: VeraMove name, one-line pitch, demo-mode indicator, backend health status, and links to the workflow routes.
- `/intake`: explains voice/document intake and can create the seeded synthetic job.
- `/confirm/:jobId`: loads the job, displays confirmation state, and confirms it.
- `/calls/:jobId`: loads the job, starts three calls, and exposes a negotiation action once quotes are ready.
- `/report/:jobId`: loads and renders the evidence-backed recommendation.

Every data page uses one shared typed API client and has visible loading and error states. Route components import generated OpenAPI types; there is no handwritten parallel set of frontend domain interfaces.

## Configuration and Fixtures

`configs/moving.yaml` is the single source for intake questions, required fields, fee categories, negotiation levers, structured outcomes, honesty constraints, and the 30-percent-below-median red-flag threshold.

Demo fixtures are explicit synthetic data and contain no real phone numbers, addresses, recordings, or personal information. The fixtures include:

- one two-bedroom move;
- three fictional vendors and policy cards;
- three initial quotes covering transparent, hidden-fee, and premium behaviors;
- one improved negotiated quote;
- transcript evidence and recording links;
- one ranked recommendation.

## Persistence Boundary

A `JobRepository` protocol provides the operations used by orchestration. `InMemoryJobRepository` is process-local, thread-safe enough for development, and always used by default. Supabase/PostgreSQL is represented by one migration, environment variables, and an integration boundary document, not by a runtime dependency or incomplete adapter.

The migration creates `jobs`, `vendors`, `calls`, `quotes`, `transcript_evidence`, `recommendations`, and `event_log` with UUID primary keys, timestamps, foreign keys, useful indexes, versioned JSONB payloads, and a unique webhook idempotency key.

## Developer Experience

`python scripts/bootstrap.py` creates `.venv`, installs backend and frontend dependencies, exports OpenAPI, generates TypeScript types, and prints next steps. It is safe to rerun.

`python scripts/dev.py` starts Uvicorn on port 8000 and Vite on port 5173, forwards output, detects early process exits, and terminates both children on Ctrl+C.

`python scripts/check.py` runs Ruff, pytest, OpenAPI export, TypeScript generation, frontend typecheck, frontend tests, and the production build in order, stopping on the first failure with a nonzero status.

Generation uses `openapi-typescript` from the frontend toolchain. The export script imports the FastAPI app and writes a deterministic JSON document to `packages/contracts/openapi.json`.

## Testing and Verification

Backend tests verify:

- contract validation and serialization;
- legal and illegal job transitions;
- every requested endpoint;
- confirmation locking;
- three mock call records and itemized quote outcomes;
- measurable negotiated improvement using verified evidence;
- evidence-backed report ranking;
- webhook idempotency and mock vendor discovery.

Frontend tests verify the homepage and route placeholders, loading/error behavior at the shared-client boundary, and generated-type compatibility. TypeScript strict mode and the production build catch contract drift.

CI installs Python 3.11 and a current Node LTS release, installs declared dependencies, and runs `python scripts/check.py` for pull requests and pushes to `main`. It has no deployment steps or secrets.

Acceptance is proven locally by running `python scripts/bootstrap.py`, `python scripts/check.py`, starting `python scripts/dev.py`, checking `/health`, `/docs`, and the frontend, and exercising the seeded API flow.

## Documentation and Team Boundaries

The root README documents product intent, architecture, structure, setup, environment variables, mock mode, commands, routes, branch conventions, known limitations, synthetic data, and future nullable VeraAI identifiers.

`AGENTS.md` records non-negotiable requirements, no-secrets and no-real-PII rules, contract-change procedure, required PR checks, and the exact temporary Member 1 through Member 4 directory ownership supplied in the project brief. Contributors must not rewrite another member's subsystem.

`CONTRIBUTING.md`, a placeholder `CODEOWNERS`, the pull-request template, and architecture/API/integration documents reinforce those boundaries.

## Security and Privacy

No secrets or credentials are committed. `.env.example` contains names and safe defaults only. No real external API requests occur. No real phone numbers, home addresses, recordings, local databases, or personal data are stored. All demo content is labeled synthetic.

## Assumptions

- Python 3.11 or newer and Node.js 20.19 or newer are acceptable local prerequisites.
- The empty workspace should be initialized as a Git repository with `main` as its initial branch.
- Mock call and negotiation operations may complete synchronously because the starter proves contracts and flow, not telephony timing.
- `POST /api/jobs` accepts a complete `JobSpecV1` and therefore enters `intake_complete` immediately; `draft` remains a supported domain state for future incremental intake.
- `GET /api/jobs/{job_id}` returns an aggregate view containing the job specification, state, calls, and quotes so all simple frontend pages can use one read endpoint.
- Synthetic example URLs use `example.com`, and synthetic phone-like identifiers are non-dialable labels rather than realistic numbers.
- A root package manager or monorepo framework is unnecessary.

## Completion Boundary

The starter is complete only when all requested files exist, the mock workflow is testable, bootstrap and validation commands pass from a clean environment without credentials, both development servers run on their specified ports, the final tree is inspected, and the repository contains a final commit named `chore: bootstrap VeraMove hackathon repository`.
