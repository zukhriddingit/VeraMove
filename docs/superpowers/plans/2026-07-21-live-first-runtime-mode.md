# Live-First Runtime Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every new browser session start in Live mode while preserving Demo as a session-scoped, explicit fallback.

**Architecture:** `apps/web/src/api/client.ts` remains the sole runtime-mode owner. It migrates away from persistent `localStorage`, hydrates an optional `sessionStorage` override after React mounts, and keeps presentation components storage-agnostic. The landing page's confirmed-offline fallback uses the existing `setRuntimeMode()` redirect contract so the selected adapter and demo route cannot disagree.

**Tech Stack:** TypeScript 5.8, React 19, TanStack Router, Vitest 3, browser `sessionStorage`

## Global Constraints

- Every newly opened browser session starts VeraMove in Live mode against the configured FastAPI backend.
- Demo mode remains a deliberate fallback for a confirmed live failure or an explicit demo flow.
- Do not silently switch to Demo during Render cold-start retries.
- Missing, invalid, or inaccessible browser storage must retain the environment default.
- Do not change backend behavior, API contracts, provider integrations, or product design.

---

## File map

- Modify `apps/web/src/api/client.ts`: session persistence, legacy cleanup, hydration, redirects.
- Modify `apps/web/src/api/client.test.ts`: Live-first migration and session-switch regression tests.
- Modify `apps/web/src/routes/index.tsx`: adapter-aware confirmed-offline fallback.

### Task 1: Session-scoped runtime mode

**Files:**
- Modify: `apps/web/src/api/client.ts:29-84`
- Test: `apps/web/src/api/client.test.ts`

**Interfaces:**
- Consumes: `RuntimeMode = "demo" | "live"` and `readEnvMode(): RuntimeMode`.
- Produces: `hydrateRuntimeMode(): void`, `getRuntimeMode(): RuntimeMode`, and `setRuntimeMode(next, options): void`.

- [ ] **Step 1: Add failing runtime-mode tests**

Add this storage fake and dynamic loader to `apps/web/src/api/client.test.ts`:

```ts
function storageWith(entries: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(entries));
  return {
    get length() { return values.size; },
    clear: vi.fn(() => values.clear()),
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    key: vi.fn((index: number) => [...values.keys()][index] ?? null),
    removeItem: vi.fn((key: string) => values.delete(key)),
    setItem: vi.fn((key: string, value: string) => values.set(key, value)),
  };
}

async function loadRuntimeClient(options?: {
  session?: Record<string, string>;
  legacy?: Record<string, string>;
}) {
  vi.resetModules();
  const sessionStorage = storageWith(options?.session);
  const localStorage = storageWith(options?.legacy);
  const assign = vi.fn();
  const reload = vi.fn();
  vi.stubGlobal("window", { sessionStorage, localStorage, location: { assign, reload } });
  const client = await import("./client");
  return { client, sessionStorage, localStorage, assign, reload };
}
```

Add these tests:

```ts
describe("runtime mode persistence", () => {
  it("ignores and removes a legacy persistent Demo choice", async () => {
    const { client, localStorage } = await loadRuntimeClient({
      legacy: { "veramove.runtimeMode": "demo" },
    });
    client.hydrateRuntimeMode();
    expect(client.getRuntimeMode()).toBe("live");
    expect(localStorage.removeItem).toHaveBeenCalledWith("veramove.runtimeMode");
  });

  it("restores Demo only from the current session", async () => {
    const { client } = await loadRuntimeClient({
      session: { "veramove.runtimeMode.session": "demo" },
    });
    client.hydrateRuntimeMode();
    expect(client.getRuntimeMode()).toBe("demo");
  });

  it("stores Demo in the session before redirecting", async () => {
    const { client, sessionStorage, assign } = await loadRuntimeClient();
    client.setRuntimeMode("demo", { redirectTo: "/confirm/demo-job-1" });
    expect(sessionStorage.setItem).toHaveBeenCalledWith(
      "veramove.runtimeMode.session", "demo",
    );
    expect(assign).toHaveBeenCalledWith("/confirm/demo-job-1");
  });

  it("stores an explicit return to Live in the session", async () => {
    const { client, sessionStorage, reload } = await loadRuntimeClient({
      session: { "veramove.runtimeMode.session": "demo" },
    });
    client.hydrateRuntimeMode();
    client.setRuntimeMode("live");
    expect(sessionStorage.setItem).toHaveBeenCalledWith(
      "veramove.runtimeMode.session", "live",
    );
    expect(reload).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run the tests and confirm failure**

Run `npm --prefix apps/web test -- --run src/api/client.test.ts`.

Expected: FAIL because `hydrateRuntimeMode` does not exist and choices use `localStorage`.

- [ ] **Step 3: Implement session persistence and legacy cleanup**

Replace the storage definitions in `apps/web/src/api/client.ts` with:

```ts
const SESSION_STORAGE_KEY = "veramove.runtimeMode.session";
const LEGACY_STORAGE_KEY = "veramove.runtimeMode";

function readSessionMode(): RuntimeMode | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    return value === "demo" || value === "live" ? value : null;
  } catch {
    return null;
  }
}

function removeLegacyStoredMode(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // Storage can be unavailable; the Live production default stays active.
  }
}
```

Keep `currentMode = readEnvMode()` and add:

```ts
export function hydrateRuntimeMode(): void {
  removeLegacyStoredMode();
  const storedMode = readSessionMode();
  if (storedMode) publishMode(storedMode);
}
```

Call `hydrateRuntimeMode()` from the existing `useEffect`. Update `setRuntimeMode()` to use:

```ts
try {
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, next);
  window.localStorage.removeItem(LEGACY_STORAGE_KEY);
} catch {
  // Storage can be unavailable in privacy modes; navigation still works.
}
```

- [ ] **Step 4: Run focused tests**

Run `npm --prefix apps/web test -- --run src/api/client.test.ts`.

Expected: all client tests PASS.

- [ ] **Step 5: Commit the runtime boundary**

```bash
git add apps/web/src/api/client.ts apps/web/src/api/client.test.ts
git commit -m "fix(web): default new sessions to live mode"
```

### Task 2: Correct the confirmed-offline fallback

**Files:**
- Modify: `apps/web/src/routes/index.tsx:54-57`
- Test: `apps/web/src/api/client.test.ts`

**Interfaces:**
- Consumes: `setRuntimeMode("demo", { redirectTo: string }): void` from Task 1.
- Produces: an `onUseDemo` callback that selects Demo before opening the synthetic job.

- [ ] **Step 1: Replace the navigation-only fallback**

Use this callback in `apps/web/src/routes/index.tsx`:

```tsx
<HealthIndicator
  onUseDemo={() =>
    setRuntimeMode("demo", { redirectTo: `/confirm/${DEMO_JOB_ID}` })
  }
/>
```

It remains hidden until the existing health state is confirmed `offline` or `degraded`.

- [ ] **Step 2: Run type checking and focused tests**

Run:

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web test -- --run src/api/client.test.ts
```

Expected: both commands PASS.

- [ ] **Step 3: Commit the fallback wiring**

```bash
git add apps/web/src/routes/index.tsx
git commit -m "fix(web): make demo fallback select its adapter"
```

### Task 3: Repository verification and deployment

**Files:**
- Verify: `apps/web/src/api/client.ts`
- Verify: `apps/web/src/api/client.test.ts`
- Verify: `apps/web/src/routes/index.tsx`

**Interfaces:**
- Consumes: the Live-first runtime boundary and adapter-aware fallback.
- Produces: clean, pushed `main` and `deploy/veramove-demo` branches with verified public behavior.

- [ ] **Step 1: Run the canonical gate**

Run `python scripts/check.py`.

Expected: Ruff, 481+ pytest tests, OpenAPI export, API type generation, TypeScript, Vitest, and the Vite production build all PASS.

- [ ] **Step 2: Inspect final Git state**

Run:

```bash
git status --short --branch
git log -3 --oneline --decorate
```

Expected: clean `main` with the design and implementation commits above the previous production revision.

- [ ] **Step 3: Push both deployment branches**

Run:

```bash
git push origin main
git push origin main:deploy/veramove-demo
```

Expected: both branches advance without a force push.

- [ ] **Step 4: Verify a fresh public browser session**

Open `https://deal-mover-ai.lovable.app/` with empty session storage.

Expected:

- Header shows **Live · connected**.
- Health reaches **API online** after any cold start.
- Legacy `localStorage["veramove.runtimeMode"] = "demo"` is ignored and removed.
- Explicit Demo works within the active session.
- A newly opened browser session returns to **Live · connected**.

