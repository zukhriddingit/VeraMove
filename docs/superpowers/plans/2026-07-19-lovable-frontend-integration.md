# Lovable Frontend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `apps/web` with the completed Lovable UI while retaining the canonical typed VeraMove API integration and passing every repository gate.

**Architecture:** Perform a one-time excluded rsync import on a dedicated branch based on the live backend branch. Regenerate FastAPI OpenAPI types, then expose all browser/server communication through one typed client that incorporates Lovable runtime and cold-start behavior.

**Tech Stack:** React 18, TypeScript, Vite, npm, openapi-typescript, Vitest, FastAPI OpenAPI

## Global Constraints

- Do not redesign the imported Lovable interface.
- Do not change backend behavior unless a minimal build path or CORS correction is proven necessary.
- Do not add provider secrets or direct browser calls to OpenAI, Tavily, Supabase, ElevenLabs, or Twilio.
- Keep npm, one `package-lock.json`, one `VITE_API_BASE_URL`, and generated OpenAPI types.
- Do not commit until all checks pass.

---

### Task 1: Create the integration branch and import the Lovable tree

**Files:**
- Replace: `apps/web/**`
- Preserve for reconciliation: `apps/web/src/api/schema.d.ts`, `apps/web/src/api/client.ts`

**Interfaces:**
- Consumes: `deploy/veramove-demo`, sibling clone `veramove-lovable-ui`
- Produces: imported Lovable application rooted at `apps/web`

- [ ] Verify the worktree is clean and `origin/main` is an ancestor of `deploy/veramove-demo`.
- [ ] Create `feat/integrate-lovable-frontend` from `deploy/veramove-demo`.
- [ ] Clone `git@github.com:zukhriddingit/veramove-lovable-ui.git` into a temporary sibling directory.
- [ ] Save the canonical schema/client to a mode-700 temporary backup directory.
- [ ] Run the reviewed `rsync --delete` import with `.git`, `.github`, `.env*`, `node_modules`,
      `dist`, root `README.md`, and root `LICENSE` excluded.
- [ ] Confirm no environment file, Git metadata, dependency directory, or build output was imported.

### Task 2: Reconcile package and API boundaries

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Generate: `apps/web/src/api/schema.d.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify as required: `apps/web/src/**/*.{ts,tsx}`

**Interfaces:**
- Consumes: `packages/contracts/openapi.json`, backed-up main client, Lovable runtime helpers
- Produces: one generated schema and one typed `api` client used by presentation code

- [ ] Keep npm and remove imported non-npm lockfiles.
- [ ] Run `python scripts/export_openapi.py` and `npm --prefix apps/web run generate:api`.
- [ ] Diff the backed-up client against the imported client.
- [ ] Preserve every current API operation and generated request/response type.
- [ ] Preserve Lovable runtime-mode, Render cold-start/health, `VITE_API_BASE_URL`, and normalized
      FastAPI errors in the centralized client.
- [ ] Search for direct `fetch` and provider SDK/API usage; route UI calls through the client.
- [ ] Search for duplicate handwritten JobSpec/Quote/Call/Evidence/Recommendation/Report models and
      replace them with generated aliases or view-only types.

### Task 3: Validate the integrated frontend and repository

**Files:**
- Modify as failures require: `apps/web/**`
- Modify if required: `.env.example`, frontend documentation

**Interfaces:**
- Consumes: integrated frontend and canonical backend contract
- Produces: buildable, testable hackathon demo branch with a reviewed uncommitted diff

- [ ] Run `npm --prefix apps/web install` to produce the canonical npm lockfile.
- [ ] Run `npm --prefix apps/web run typecheck`; fix all errors without redesigning UI.
- [ ] Run `npm --prefix apps/web test`; fix integration regressions.
- [ ] Run `npm --prefix apps/web run build`; fix production-only failures.
- [ ] Run `python scripts/check.py`; fix the complete repository gate.
- [ ] Review `git diff --check`, `git status`, generated artifacts, environment references, and secret
      scans.
- [ ] Report changed files, API-client decisions, generated-type preservation, environment variables,
      commands, and remaining risks. Do not commit.
