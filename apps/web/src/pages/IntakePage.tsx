import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type JobRecord, type JobSpecV1 } from "../api/client";
import { ErrorState } from "../components/AsyncState";

const voiceIntakeJob: JobSpecV1 = {
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

// Simulated "document parse" output. In production this would come from an OpenAI
// document-parsing endpoint (Zukhriuddin's subsystem); here it's a clearly labeled
// synthetic result so the frontend loop is demonstrable without a new backend route,
// since POST /api/jobs already accepts a full JobSpecV1 from either intake path.
const documentIntakeJob: JobSpecV1 = {
  job_id: "22222222-2222-4222-8222-222222222222",
  version: "1.0",
  move_date: "2026-09-02",
  date_flexible: false,
  origin: {
    address_summary: "Synthetic origin in Brookline, Massachusetts",
    dwelling_type: "house",
    floors: 2,
    stairs: 8,
    elevator_access: false,
    parking_distance_feet: 40,
    access_notes: "Synthetic driveway access, no permit required.",
  },
  destination: {
    address_summary: "Synthetic destination in Newton, Massachusetts",
    dwelling_type: "house",
    floors: 2,
    stairs: 6,
    elevator_access: false,
    parking_distance_feet: 25,
    access_notes: "Synthetic direct driveway access.",
  },
  bedroom_count: 3,
  inventory: [
    {
      item_id: "52000000-0000-4000-8000-000000000001",
      name: "Sectional sofa",
      quantity: 1,
      room: "Living room",
      oversized: true,
      fragile: false,
      notes: "May require disassembly for doorways.",
    },
    {
      item_id: "52000000-0000-4000-8000-000000000002",
      name: "Upright piano",
      quantity: 1,
      room: "Living room",
      oversized: true,
      fragile: true,
      notes: "Specialty handling requested.",
    },
  ],
  oversized_or_fragile_items: ["Sectional sofa", "Upright piano"],
  services: { packing: true, disassembly: true, storage: false, storage_days: null },
  insurance_preference: "Full-value protection options requested",
  confirmed: false,
  confirmed_at: null,
  source_context: { intake_method: "document", vera_user_id: null, vera_property_id: null },
};

type IntakeMode = "voice" | "document";

export function IntakePage() {
  const [mode, setMode] = useState<IntakeMode>("voice");
  const [fileName, setFileName] = useState<string | null>(null);
  const [record, setRecord] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setFileName(file ? file.name : null);
  }

  async function createDemoJob() {
    setLoading(true);
    setError(null);
    try {
      const jobSpec = mode === "voice" ? voiceIntakeJob : documentIntakeJob;
      setRecord(await api.createJob(jobSpec));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create job");
    } finally {
      setLoading(false);
    }
  }

  const canSubmit = mode === "voice" || Boolean(fileName);

  return (
    <section className="card space-y-5">
      <p className="text-sm font-bold uppercase tracking-widest text-teal">Step 1</p>
      <h1 className="text-3xl font-bold">Voice or document intake</h1>
      <p>
        Both intake paths produce the same typed JobSpec. This starter submits a clearly synthetic
        move without credentials or real personal data.
      </p>

      <div className="flex gap-3" role="tablist" aria-label="Intake method">
        <button
          className={mode === "voice" ? "button" : "link-button"}
          onClick={() => {
            setMode("voice");
            setRecord(null);
            setError(null);
          }}
          type="button"
          aria-pressed={mode === "voice"}
        >
          Voice intake
        </button>
        <button
          className={mode === "document" ? "button" : "link-button"}
          onClick={() => {
            setMode("document");
            setRecord(null);
            setError(null);
          }}
          type="button"
          aria-pressed={mode === "document"}
        >
          Document upload
        </button>
      </div>

      {mode === "voice" ? (
        <p className="text-sm text-ink/70">
          Simulates a completed ElevenLabs voice interview: rooms, inventory, stairs, and access
          notes are already captured.
        </p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-ink/70">
            Upload an existing quote or inventory photo. This starter does not perform real document
            parsing — it demonstrates that a document-derived JobSpec reaches the same schema and the
            same confirmation step as a voice-derived one.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf"
            onChange={handleFileSelected}
            className="block text-sm"
          />
          {fileName ? (
            <p className="text-sm font-semibold text-teal">Selected: {fileName} (simulated parse)</p>
          ) : (
            <p className="text-sm text-ink/50">No file selected yet.</p>
          )}
        </div>
      )}

      {error ? <ErrorState message={error} /> : null}

      {!record ? (
        <button className="button" disabled={loading || !canSubmit} onClick={createDemoJob} type="button">
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
