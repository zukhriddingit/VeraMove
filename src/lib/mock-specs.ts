import type { JobSpecV1 } from "./api";

function newId(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now().toString(36)}_${rand}`;
}

// Both fixtures are clearly-synthetic demo data — no real PII.

export function buildVoiceIntakeSpec(): JobSpecV1 {
  const jobId = newId("job");
  const moveDate = new Date();
  moveDate.setDate(moveDate.getDate() + 21);
  return {
    job_id: jobId,
    version: "1.0",
    move_date: moveDate.toISOString().slice(0, 10),
    date_flexible: true,
    origin: {
      address_summary: "[DEMO] 482 Linden Apt 3B, Oakland CA",
      dwelling_type: "apartment",
      floors: 1,
      stairs: 18,
      elevator_access: false,
      parking_distance_feet: 60,
      access_notes: "Narrow stairwell; permit parking on street.",
    },
    destination: {
      address_summary: "[DEMO] 1290 Harbor View Condos #504, Alameda CA",
      dwelling_type: "condo",
      floors: 1,
      stairs: false,
      elevator_access: true,
      parking_distance_feet: 25,
      access_notes: "Freight elevator must be reserved 48h ahead.",
    },
    bedroom_count: 2,
    inventory: [
      { item_id: "i1", name: "Queen bed frame + mattress", quantity: 1, room: "bedroom", oversized: false, fragile: false },
      { item_id: "i2", name: "6-seat dining table", quantity: 1, room: "dining", oversized: true, fragile: false, notes: "Requires disassembly" },
      { item_id: "i3", name: "55\" TV", quantity: 1, room: "living", oversized: false, fragile: true },
      { item_id: "i4", name: "Bookshelves", quantity: 3, room: "office", oversized: false, fragile: false },
      { item_id: "i5", name: "Standard boxes (kitchen + misc)", quantity: 28, room: "kitchen", oversized: false, fragile: false },
    ],
    oversized_or_fragile_items: ["6-seat dining table (oversized)", "55\" TV (fragile)"],
    services: { packing: true, disassembly: true, storage: false },
    insurance_preference: "standard_released_value",
    confirmed: false,
    confirmed_at: null,
    source_context: {
      intake_method: "voice",
      vera_user_id: "demo_user_voice_001",
      vera_property_id: "demo_prop_oak_482",
    },
  };
}

export function buildDocumentIntakeSpec(): JobSpecV1 {
  const jobId = newId("job");
  const moveDate = new Date();
  moveDate.setDate(moveDate.getDate() + 35);
  return {
    job_id: jobId,
    version: 1,
    move_date: moveDate.toISOString().slice(0, 10),
    date_flexible: false,
    origin: {
      address_summary: "[DEMO] 77 Meadowbrook Ln, Palo Alto CA",
      dwelling_type: "single_family_house",
      floors: 2,
      stairs: true,
      elevator_access: false,
      parking_distance_feet: 15,
      access_notes: "Driveway access; large hedge near front door.",
    },
    destination: {
      address_summary: "[DEMO] 4415 Fern Hollow Rd, San Jose CA",
      dwelling_type: "single_family_house",
      floors: 2,
      stairs: true,
      elevator_access: false,
      parking_distance_feet: 30,
      access_notes: "HOA quiet hours after 8pm.",
    },
    bedroom_count: 3,
    inventory: [
      { item_id: "d1", name: "Upright piano", quantity: 1, room: "living", oversized: true, fragile: true, notes: "Specialty movers required" },
      { item_id: "d2", name: "Sectional sofa (4-piece)", quantity: 1, room: "living", oversized: true, fragile: false },
      { item_id: "d3", name: "King bed frame + mattress", quantity: 1, room: "primary_bedroom", oversized: true, fragile: false },
      { item_id: "d4", name: "Twin beds", quantity: 2, room: "bedroom", oversized: false, fragile: false },
      { item_id: "d5", name: "Wine fridge", quantity: 1, room: "kitchen", oversized: false, fragile: true },
      { item_id: "d6", name: "Framed artwork", quantity: 8, room: "living", oversized: false, fragile: true },
      { item_id: "d7", name: "Standard boxes", quantity: 62, room: "kitchen", oversized: false, fragile: false },
    ],
    oversized_or_fragile_items: [
      "Upright piano (oversized + fragile)",
      "Sectional sofa (oversized)",
      "King bed frame (oversized)",
      "Wine fridge (fragile)",
      "Framed artwork x8 (fragile)",
    ],
    services: { packing: true, disassembly: true, storage: true, storage_days: 14 },
    insurance_preference: "full_value_protection",
    confirmed: false,
    confirmed_at: null,
    source_context: {
      intake_method: "document",
      vera_user_id: "demo_user_doc_002",
      vera_property_id: "demo_prop_pa_77",
    },
  };
}
