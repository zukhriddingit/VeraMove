import { describe, expect, it } from "vitest";
import type { VendorDiscoveryResponse } from "@/api/client";
import { toJobEventView, toVendorViews } from "./adapters";

describe("OpenAPI response adapters", () => {
  it("unwraps the canonical vendor discovery envelope", () => {
    const response: VendorDiscoveryResponse = {
      source: "synthetic_mock",
      vendors: [
        {
          vendor_id: "00000000-0000-4000-8000-000000000001",
          name: "Example Moving Co.",
          slug: "example-moving-co",
          behavior_summary: "Transparent synthetic demo vendor",
          contact_label: "Reserved example contact",
          service_areas: ["Example City"],
          data_classification: "synthetic",
        },
      ],
    };

    expect(toVendorViews(response)).toEqual([
      {
        id: "00000000-0000-4000-8000-000000000001",
        name: "Example Moving Co.",
        kind: "transparent",
      },
    ]);
  });

  it("maps the canonical event envelope without inventing event data", () => {
    expect(
      toJobEventView({
        occurred_at: "2026-07-19T01:00:00Z",
        event_type: "call_completed",
        job_id: "00000000-0000-4000-8000-000000000002",
        metadata: { message: "Synthetic call completed" },
      }),
    ).toEqual({
      ts: "2026-07-19T01:00:00Z",
      type: "call_completed",
      jobId: "00000000-0000-4000-8000-000000000002",
      message: "Synthetic call completed",
    });
  });
});
