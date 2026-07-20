import { describe, expect, it } from "vitest";
import type { JobRecord, VendorDiscoveryResponse } from "@/api/client";
import { mergeJobViewIntoSpec, toJobEventView, toJobView, toVendorViews } from "./adapters";

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

  it("blocks only on canonical fields exposed by the review editor", () => {
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

    expect(toJobView(record).missingFields).toEqual(["access.origin"]);
  });

  it("merges editable review fields without discarding hidden canonical facts", () => {
    const current = {
      job_id: "00000000-0000-4000-8000-000000000003",
      version: "1.0",
      intake_source: "voice",
      move_date: "2026-08-16",
      date_flexible: true,
      origin: {
        address_summary: "Old Origin, MA",
        dwelling_type: "apartment",
        floors: 2,
        stairs: 18,
        elevator_access: false,
        parking_distance_feet: 80,
        access_notes: "Narrow synthetic hallway",
      },
      destination: {
        address_summary: "Old Destination, NY",
        dwelling_type: "apartment",
        floors: 4,
        stairs: 44,
        elevator_access: true,
        parking_distance_feet: 25,
        access_notes: "Synthetic loading dock",
      },
      bedroom_count: 2,
      inventory: [
        {
          item_id: "00000000-0000-4000-8000-000000000004",
          name: "Synthetic sofa",
          quantity: 1,
          room: "living room",
          oversized: true,
          fragile: false,
          notes: "Keep wrapped",
        },
      ],
      oversized_or_fragile_items: ["Synthetic sofa"],
      services: { packing: false, disassembly: true, storage: false, storage_days: null },
      insurance_preference: "standard released-value coverage",
      confirmed: false,
      confirmed_at: null,
      locked_version: null,
      source_context: { vera_user_id: null, vera_property_id: null },
      data_classification: "synthetic",
    } satisfies JobRecord["job_spec"];
    const view = toJobView({
      job_spec: current,
      state: "intake_complete",
      calls: [],
      quotes: [],
      recommendation: null,
      created_at: "2026-07-19T01:00:00Z",
      updated_at: "2026-07-19T01:00:00Z",
    });
    const draft = {
      ...view,
      homeType: "condo",
      bedrooms: 3,
      move: {
        ...view.move,
        originCity: "New Origin",
        originState: "NC",
        destinationCity: "New Destination",
        destinationState: "SC",
        date: "2026-08-20",
        flexibilityDays: 0,
      },
      access: {
        ...view.access,
        originFloor: 3,
        originElevator: true,
        destinationFloor: 5,
        destinationElevator: false,
        longCarryFt: 120,
      },
      inventory: [{ item: "Synthetic sofa", qty: 2, notes: "Blanket wrap" }],
      services: { packing: true, insuranceTier: "full-value" as const },
      extras: {
        disassembly: false,
        storage: false,
        oversizedOrFragile: ["Synthetic mirror"],
      },
      notes: "Call on synthetic arrival",
    };

    const replacement = mergeJobViewIntoSpec(current, draft);

    expect(replacement).toMatchObject({
      job_id: current.job_id,
      version: "1.0",
      intake_source: "voice",
      move_date: "2026-08-20",
      date_flexible: false,
      bedroom_count: 3,
      origin: {
        address_summary: "New Origin, NC",
        dwelling_type: "condo",
        floors: 3,
        stairs: 18,
        elevator_access: true,
        parking_distance_feet: 120,
        access_notes: "Call on synthetic arrival",
      },
      destination: {
        address_summary: "New Destination, SC",
        dwelling_type: "condo",
        floors: 5,
        stairs: 44,
        elevator_access: false,
        parking_distance_feet: 25,
        access_notes: "Synthetic loading dock",
      },
      inventory: [
        {
          item_id: "00000000-0000-4000-8000-000000000004",
          name: "Synthetic sofa",
          quantity: 2,
          room: "living room",
          oversized: true,
          fragile: false,
          notes: "Blanket wrap",
        },
      ],
      oversized_or_fragile_items: ["Synthetic mirror"],
      services: { packing: true, disassembly: false, storage: false, storage_days: null },
      insurance_preference: "Full-value protection",
      source_context: current.source_context,
      data_classification: "synthetic",
    });
  });
});
