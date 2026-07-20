import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

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
