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
- `services/api/app/integrations` contains protocols and adapters; mock adapters are wired by
  default, and live voice is fail-closed behind explicit settings.
- `apps/web` uses one client and OpenAPI-generated types, never parallel handwritten domain models.
- `configs/moving.yaml` owns moving-specific questions, thresholds, fee categories, and honesty rules.
- `data/demo` contains synthetic fixtures; versioned domain payloads may later persist as JSONB.

## Temporary directory ownership

Ownership is by role, not by an arbitrary member number — a prior draft of this file split one
person's work (backend + voice) across two "members" and left the narrative/submission role with no
directory at all. Fixed below.

### Prathmesh (@prathmesh-handle-tbd) — backend orchestration & voice

- `services/api/app/api`
- `services/api/app/orchestration`
- `services/api/app/repositories`
- `services/api/app/integrations/tavily`
- `agents`
- `services/api/app/integrations/elevenlabs`
- voice-related tests and fixtures

### Zukhriuddin (@zukhriddingit) — data & intelligence layer

- `services/api/app/contracts`
- `services/api/app/integrations/openai`
- `packages/contracts`
- `supabase`
- `data`
- `evals`

### Toheeb (@Olacode01) — frontend

- `apps/web`
- frontend tests

### Arsalan (@ars2711) — product narrative & submission

- `docs/submission/` (project summary, video scripts, claim ledger, requirements mapping,
  final checklist — see that folder for the full list)
- `docs/demo-ux.md` (narrative pass; Toheeb owns the underlying UX build)
- `README.md`, jointly with the relevant technical owner for setup-command accuracy
- Final review on any wording that will appear in a video, the Project Summary, or the
  submission portal, regardless of which directory it lives in. No claim about what the
  product does moves into a video or the Project Summary until it is marked verified in
  `docs/submission/claim-ledger.md` by its technical owner, and Arsalan signs off on the
  final wording before it's recorded or submitted.

Do not rewrite another member's subsystem. Propose cross-boundary changes to the owner and keep
unrelated refactors out of your branch.

## No-secrets rule

Never commit API keys, auth tokens, populated `.env` files, database credentials, recordings, or
local database files. Mock mode must remain the default. Real adapters may never silently activate;
they require explicit reviewed settings and must preserve credential-free mock behavior.

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
