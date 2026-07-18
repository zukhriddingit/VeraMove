import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type JobRecord, type JobSpecV1 } from "../api/client";
import { ErrorState } from "../components/AsyncState";

const syntheticJob: JobSpecV1 = {
  job_id: "11111111-1111-4111-8111-111111111111",
  version: "1.0",
  move_date: "2026-08-15",
  date_flexible: true,
  origin: {
    address_summary: "Synthetic origin in Cambridge, Massachusetts",
    dwelling_type: "apartment",
    floors: 3,
    stairs: 24,
    elevator_access: false,
    parking_distance_feet: 180,
    access_notes: "Synthetic curb access with a moderate carry.",
  },
  destination: {
    address_summary: "Synthetic destination in Somerville, Massachusetts",
    dwelling_type: "condo",
    floors: 2,
    stairs: 12,
    elevator_access: true,
    parking_distance_feet: 60,
    access_notes: "Synthetic loading zone available by reservation.",
  },
  bedroom_count: 2,
  inventory: [
    {
      item_id: "51000000-0000-4000-8000-000000000001",
      name: "Queen bed frame",
      quantity: 1,
      room: "Primary bedroom",
      oversized: false,
      fragile: false,
      notes: "Disassembly requested.",
    },
    {
      item_id: "51000000-0000-4000-8000-000000000003",
      name: "Glass dining table",
      quantity: 1,
      room: "Dining room",
      oversized: true,
      fragile: true,
      notes: "Protect glass top separately.",
    },
  ],
  oversized_or_fragile_items: ["Glass dining table"],
  services: { packing: false, disassembly: true, storage: false, storage_days: null },
  insurance_preference: "Full-value protection options requested",
  confirmed: false,
  confirmed_at: null,
  source_context: { intake_method: "demo", vera_user_id: null, vera_property_id: null },
};

export function IntakePage() {
  const [record, setRecord] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function createDemoJob() {
    setLoading(true);
    setError(null);
    try {
      setRecord(await api.createJob(syntheticJob));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create job");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card space-y-5">
      <p className="text-sm font-bold uppercase tracking-widest text-teal">Step 1</p>
      <h1 className="text-3xl font-bold">Voice or document intake</h1>
      <p>
        Both future intake paths produce the same typed JobSpec. This starter submits a clearly synthetic
        two-bedroom move without credentials.
      </p>
      {error ? <ErrorState message={error} /> : null}
      {!record ? (
        <button className="button" disabled={loading} onClick={createDemoJob} type="button">
          {loading ? "Creating…" : "Create synthetic job"}
        </button>
      ) : (
        <div className="space-y-3 rounded-lg bg-mint p-4">
          <p>Job created in {record.state} state.</p>
          <Link className="link-button" to={`/confirm/${record.job_spec.job_id}`}>
            Review and confirm
          </Link>
        </div>
      )}
    </section>
  );
}
