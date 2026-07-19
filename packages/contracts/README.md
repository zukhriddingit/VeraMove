# Generated API contracts

`openapi.json` is exported from FastAPI and is the canonical API contract. The frontend's
`apps/web/src/api/schema.d.ts` is generated from it with `openapi-typescript`.

Regenerate both through `python scripts/check.py`; do not hand-edit either generated file.

The v1 domain invariants, unknown-versus-zero semantics, verification states, and provenance rules
are documented in `docs/contracts-v1.md`.
