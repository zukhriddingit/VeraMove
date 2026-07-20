# Live-First Runtime Mode Design

## Goal

Every newly opened browser session starts VeraMove in Live mode against the configured FastAPI
backend. Demo mode remains a deliberate fallback for a confirmed live failure or an explicit demo
flow and must not leak into a later judge's session through persistent browser storage.

## Current problem

The frontend's environment default is already Live, but `veramove.runtimeMode` is stored in
`localStorage`. Once anyone selects Demo, that persistent value overrides the Live default for
future visits in the same browser profile. The offline fallback on the landing page also navigates
to the demo job without first switching the runtime adapter to Demo.

## Chosen approach

Use session-scoped mode persistence.

- Initialize from `VITE_DEMO_MODE` only; the deployed value remains Live by default.
- Restore an explicit mode choice from `sessionStorage`, not `localStorage`.
- Remove the legacy `localStorage` key during hydration so an old Demo choice cannot affect a new
  browser session.
- Persist later explicit switches in `sessionStorage` so Demo survives reloads within the same
  browser session but disappears when that session ends.
- If browser storage is unavailable, retain the environment default, which is Live in production.

This is preferred over resetting on every reload, which would break an active Demo fallback, and
over an expiring `localStorage` value, which could still put a judge into Demo and adds unnecessary
timing logic.

## Fallback behavior

The application does not silently switch to Demo when the API is slow. Render cold starts continue
to show the existing checking/starting states. Once the health check reaches its confirmed offline
state, the existing **Use demo** action switches the runtime adapter to Demo before redirecting to
the synthetic demo job. Existing explicit demo-flow controls may also select Demo. A user in Demo
can explicitly return to Live.

## Components and data flow

`apps/web/src/api/client.ts` remains the single owner of runtime mode state. It reads the production
default, hydrates a session-scoped override, publishes mode changes to React subscribers, and owns
storage migration. Presentation components continue to use `useRuntimeMode()` and
`setRuntimeMode()` rather than accessing browser storage directly.

The landing route changes its offline fallback callback to call `setRuntimeMode("demo", {
redirectTo })`, ensuring the selected adapter and destination agree. No provider credentials or
backend behavior changes.

## Error handling

- Missing, invalid, or inaccessible session storage never selects Demo.
- A stale legacy `localStorage` value is removed and never restored.
- Health-check latency remains Live while retries and cold-start messaging are active.
- Only a confirmed offline state exposes the health-indicator fallback action.

## Verification

Tests cover:

1. A fresh browser session starts Live when `VITE_DEMO_MODE` is not enabled.
2. A legacy `localStorage` Demo value is ignored and removed.
3. An explicit Demo choice persists only through `sessionStorage`.
4. The offline fallback selects Demo before redirecting.
5. Returning to Live updates the session-scoped choice.

Run `python scripts/check.py`, then verify the deployed app in a fresh browser session shows
**Live · connected** and still exposes a working Demo fallback after a confirmed API failure.

