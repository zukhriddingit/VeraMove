# API contract

FastAPI's generated OpenAPI document at `packages/contracts/openapi.json` is canonical. Pydantic v2
models in `services/api/app/contracts` are the editable source; `apps/web/src/api/schema.d.ts` is a
generated consumer artifact.

## Change procedure

1. Change Pydantic models and backend tests.
2. Update route response models and orchestration.
3. Run `python scripts/export_openapi.py`.
4. Run `npm --prefix apps/web run generate:api`.
5. Update typed frontend usage.
6. Run `python scripts/check.py` and commit both generated files.

Do not edit OpenAPI JSON or TypeScript schema output by hand. Do not create a second frontend model
tree. Versioned models retain their suffix (`JobSpecV1`, `QuoteV1`, `RecommendationV1`) when breaking
changes require a successor.

## Errors

Unknown resources return 404. Illegal state transitions, duplicate jobs, and unavailable reports
return 409 with `{ "error": { "code": "...", "message": "..." } }`. Pydantic input validation
returns FastAPI's standard 422 response.
