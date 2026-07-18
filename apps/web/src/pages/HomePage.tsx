import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";

export function HomePage() {
  const [health, setHealth] = useState("Checking API…");

  useEffect(() => {
    api.health()
      .then(() => setHealth("API connected"))
      .catch(() => setHealth("API unavailable — start python scripts/dev.py"));
  }, []);

  return (
    <section className="space-y-8">
      <div className="card bg-mint">
        <p className="mb-2 text-sm font-bold uppercase tracking-widest text-teal">Synthetic hackathon starter</p>
        <h1 className="text-5xl font-bold tracking-tight">VeraMove</h1>
        <p className="mt-4 max-w-2xl text-lg">
          One locked move specification, three vendor calls, and an evidence-backed negotiation.
        </p>
        <p className="mt-5 font-semibold" aria-live="polite">
          {health}
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Link className="card hover:border-teal" to="/intake">
          <h2 className="font-bold">Start synthetic intake</h2>
          <p>Use the committed two-bedroom demo move.</p>
        </Link>
        <Link className="card hover:border-teal" to="/confirm/11111111-1111-4111-8111-111111111111">
          <h2 className="font-bold">Confirm a job</h2>
          <p>Review and lock a structured JobSpec.</p>
        </Link>
        <Link className="card hover:border-teal" to="/calls/11111111-1111-4111-8111-111111111111">
          <h2 className="font-bold">Track vendor calls</h2>
          <p>Collect three comparable, itemized outcomes.</p>
        </Link>
        <Link className="card hover:border-teal" to="/report/11111111-1111-4111-8111-111111111111">
          <h2 className="font-bold">View final report</h2>
          <p>Rank vendors using quote and transcript evidence.</p>
        </Link>
      </div>
    </section>
  );
}
