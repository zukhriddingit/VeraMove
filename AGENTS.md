# VeraMove contributor instructions

## Product goal

Build a standalone moving-services negotiator that turns voice or document intake into one locked
`JobSpecV1`, calls three vendors with identical facts, negotiates with verified evidence, and returns
an evidence-backed ranked recommendation.

## Non-negotiable challenge requirements

- Both intake paths must produce the same versioned JobSpec contract.
- Confirmation must lock the JobSpec version before any vendor call.
- Exactly three initial vendor calls must use the same confirmed JobSpec.
- Call outcomes must be `itemized_quote`, `callback_commitment`, `documented_decline`, or `failed`.
- Negotiation must use a verified competing quote and measurably improve price or terms.
- Recommendations must cite transcript evidence and recording URLs.
- FastAPI-generated OpenAPI is the canonical API contract.
- `APP_MODE=mock` must run without credentials or Supabase.

## Architecture boundaries

- `services/api/app/contracts` owns Pydantic domain and API contracts.
- `services/api/app/orchestration` coordinates workflows but does not call external SDKs directly.
- `services/api/app/repositories` isolates persistence and defaults to in-memory behavior.
- `services/api/app/integrations` contains protocols and adapters; only mocks are wired.
- `apps/web` uses one client and OpenAPI-generated types, never parallel handwritten domain models.
- `configs/moving.yaml` owns moving-specific questions, thresholds, fee categories, and honesty rules.
- `data/demo` contains synthetic fixtures; versioned domain payloads may later persist as JSONB.

## Temporary directory ownership

### Member 1

- `services/api/app/api`
- `services/api/app/orchestration`
- `services/api/app/repositories`
- `services/api/app/integrations/tavily`
- scripts related to orchestration

### Member 2

- `agents`
- `services/api/app/integrations/elevenlabs`
- voice-related tests and fixtures

### Member 3

- `services/api/app/contracts`
- `services/api/app/integrations/openai`
- `packages/contracts`
- `supabase`
- `data`
- `evals`

### Member 4

- `apps/web`
- frontend tests
- demo UX documentation

Do not rewrite another member's subsystem. Propose cross-boundary changes to the owner and keep
unrelated refactors out of your branch.

## No-secrets rule

Never commit API keys, auth tokens, populated `.env` files, database credentials, recordings, or
local database files. Mock mode must remain the default. Real adapters require a separate reviewed
change and may not silently activate from this starter.

## No-real-PII rule

Never add real names, phone numbers, home addresses, customer inventories, transcripts, calls, or
moving records. Use obvious fictional labels and reserved example domains. Mark fixtures synthetic.

## Contract-change process

1. Update Pydantic contracts and backend contract tests.
2. Update affected orchestration and API tests.
3. Run `python scripts/export_openapi.py`.
4. Run `npm --prefix apps/web run generate:api`.
5. Update typed frontend call sites without creating handwritten duplicate contracts.
6. Run `python scripts/check.py`.
7. Request review from the affected backend and frontend owners.

Commit both generated artifacts when the public API changes.

## Tests required before a PR

Run `python scripts/check.py`. A PR is not ready until Ruff, pytest, OpenAPI export, frontend type
generation, TypeScript typecheck, Vitest, and the Vite production build all pass. Exercise the mock
create/confirm/calls/negotiate/report loop when changing orchestration or contracts.
