# Demo UX

The imported Lovable frontend is a TanStack Start application in `apps/web`. It preserves the
visual design while consuming the FastAPI contract through one generated-type client and a small
presentation adapter layer.

- `/` presents the product, workflow, runtime mode, and live API health.
- `/intake` supports live document-text intake and an explicitly labeled synthetic demo path.
- `/confirm/:jobId` reviews the move and locks the current JobSpec before any vendor call.
- `/calls/:jobId` shows exactly three comparable vendor-call outcomes and their evidence.
- `/negotiate/:jobId` shows verified leverage and the negotiated improvement.
- `/report/:jobId` renders the backend-provided ranking, evidence, warnings, and recommendation.

Set `VITE_API_BASE_URL` to the FastAPI origin. `VITE_DEMO_MODE=false` is the safe default; demo mode
must be selected explicitly and never activates because a live request failed. The health indicator
allows for Render cold starts and exposes retry/demo actions without silently changing modes.

Presentation components never call providers or `fetch` directly. `apps/web/src/api/client.ts` owns
all browser HTTP requests, generated contracts live in `apps/web/src/api/schema.d.ts`, and
`apps/web/src/lib/api/adapters.ts` maps canonical snake_case responses into UI-only view models.
