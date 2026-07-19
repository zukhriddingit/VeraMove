import { describe, expect, it } from "vitest";
import type { JobRecord, VendorDiscoveryResponse } from "@/api/client";
import { toJobEventView, toJobView, toVendorViews } from "./adapters";

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

  it("keeps confirmation blocked for every missing canonical access field", () => {
    const record = {
      job_spec: {
        job_id: "00000000-0000-4000-8000-000000000003",
        version: "1.0",
        intake_source: "document",
        move_date: "2026-08-20",
        date_flexible: true,
        origin: {
          address_summary: "Exampleville, MA",
          dwelling_type: "apartment",
          floors: 2,
          stairs: null,
          elevator_access: null,
          parking_distance_feet: 80,
          access_notes: null,
        },
        destination: {
          address_summary: "Sample City, NY",
          dwelling_type: null,
          floors: 4,
          stairs: null,
          elevator_access: true,
          parking_distance_feet: null,
          access_notes: null,
        },
        bedroom_count: 2,
        inventory: [
          {
            item_id: "00000000-0000-4000-8000-000000000004",
            name: "Synthetic sofa",
            quantity: 1,
            room: "living room",
            oversized: false,
            fragile: false,
            notes: null,
          },
        ],
        oversized_or_fragile_items: [],
        services: { packing: false, disassembly: false, storage: false, storage_days: null },
        insurance_preference: "standard released-value coverage",
        confirmed: false,
        confirmed_at: null,
        locked_version: null,
        source_context: { vera_user_id: null, vera_property_id: null },
        data_classification: "synthetic",
      },
      state: "intake_complete",
      calls: [],
      quotes: [],
      recommendation: null,
      created_at: "2026-07-19T01:00:00Z",
      updated_at: "2026-07-19T01:00:00Z",
    } as JobRecord;

    expect(toJobView(record).missingFields).toEqual([
      "homeType",
      "access.origin",
      "access.destination",
    ]);
  });
});
