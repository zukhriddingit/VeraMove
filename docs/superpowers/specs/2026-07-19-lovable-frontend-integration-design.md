# Lovable Frontend Integration Design

## Goal

Import `zukhriddingit/veramove-lovable-ui` into the VeraMove monorepo as a reviewed one-time
replacement of `apps/web`, while preserving the deployed backend, FastAPI-generated OpenAPI types,
and a single centralized browser API client.

## Chosen approach

Use a one-time `rsync --delete` import from a sibling clone. Do not use a submodule, subtree, or
ongoing bidirectional synchronization. Create `feat/integrate-lovable-frontend` from
`deploy/veramove-demo`, because `origin/main` is an ancestor of that branch and the deployment branch
contains the completed live backend work.

## Boundaries

- Preserve the Lovable interface and page design.
- Keep npm and the monorepo's `apps/web/package-lock.json`; remove conflicting imported lockfiles.
- Treat `packages/contracts/openapi.json` and generated `apps/web/src/api/schema.d.ts` as canonical.
- Keep one `apps/web/src/api/client.ts`, one `VITE_API_BASE_URL`, and one normalized FastAPI error path.
- Presentation components must call the centralized API module instead of `fetch` or provider SDKs.
- Remove handwritten duplicates of backend `JobSpec`, `Quote`, `Call`, `Evidence`,
  `Recommendation`, and `Report` contracts.
- Never expose OpenAI, Tavily, Supabase, ElevenLabs, Twilio, or backend-only credentials in the web
  bundle.
- Do not alter backend behavior. A backend or CORS edit is allowed only if the imported build proves
  a minimal path/configuration correction is required.

## Integration flow

1. Back up the current generated schema and API client outside the repository.
2. Import the Lovable repository into `apps/web` with Git metadata, environment files, dependencies,
   build output, root documentation, and licenses excluded.
3. Restore the monorepo package-manager contract, regenerate OpenAPI/types, and compare clients.
4. Reconcile Lovable runtime-mode, health, cold-start, and error UX with every current backend API
   operation.
5. Replace direct component fetches and duplicate domain models with generated types/client calls.
6. Run TypeScript checking, Vitest, production build, and the full `python scripts/check.py` gate.

## Error and runtime behavior

The client owns base-URL selection, JSON headers, response parsing, FastAPI error normalization, and
Render cold-start/health behavior. UI components receive typed values or normalized `Error` objects.
Provider calls and credentials remain server-side.

## Acceptance criteria

- The Lovable design builds from `apps/web` without visual redesign.
- Generated OpenAPI types are present and used by the client and domain-facing components.
- No direct `fetch` exists outside the centralized client/runtime helper.
- Only npm lockfiles remain for `apps/web`.
- Frontend typecheck, tests, production build, and `python scripts/check.py` all pass.
- No commit is created until all checks pass and the final diff is reviewed.
