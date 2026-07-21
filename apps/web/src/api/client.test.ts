import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

function storageWith(entries: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(entries));
  return {
    get length() {
      return values.size;
    },
    clear: vi.fn(() => values.clear()),
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    key: vi.fn((index: number) => [...values.keys()][index] ?? null),
    removeItem: vi.fn((key: string) => {
      values.delete(key);
    }),
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
  vi.stubGlobal("window", {
    sessionStorage,
    localStorage,
    location: { assign, reload },
  });
  const client = await import("./client");
  return { client, sessionStorage, localStorage, assign, reload };
}

describe("API error normalization", () => {
  it("surfaces the backend domain-conflict message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "domain_conflict",
              message: "JobSpec cannot be confirmed until destination access is complete.",
            },
          }),
          {
            status: 409,
            statusText: "Conflict",
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(apiFetch("/api/jobs/synthetic/confirm", { method: "POST" })).rejects.toEqual(
      expect.objectContaining({
        status: 409,
        detail: "JobSpec cannot be confirmed until destination access is complete.",
      }),
    );
  });
});

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
      "veramove.runtimeMode.session",
      "demo",
    );
    expect(assign).toHaveBeenCalledWith("/confirm/demo-job-1");
  });

  it("stores an explicit return to Live in the current session", async () => {
    const { client, sessionStorage, reload } = await loadRuntimeClient({
      session: { "veramove.runtimeMode.session": "demo" },
    });
    client.hydrateRuntimeMode();

    client.setRuntimeMode("live");

    expect(sessionStorage.setItem).toHaveBeenCalledWith(
      "veramove.runtimeMode.session",
      "live",
    );
    expect(reload).toHaveBeenCalledOnce();
  });
});
