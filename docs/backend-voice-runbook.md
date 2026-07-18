# Backend voice smoke and release runbook

This runbook is for the backend orchestration and voice slice. Mock mode is the normal development,
test, demo, and CI path. Live voice is an exceptional, human-supervised check against one opted-in
test destination; it is not a proof of the complete intake-to-report workflow.

## Deterministic mock smoke test

From the repository root, bootstrap dependencies and run every repository gate:

```bash
python scripts/bootstrap.py
python scripts/check.py
```

Start the API and web app in a first terminal:

```bash
APP_MODE=mock python scripts/dev.py
```

In a second terminal, run the HTTP workflow below in order. It needs only `curl` and the repository
virtual environment; it does not require `jq`, credentials, Supabase, or network access beyond the
local API.

1. Create one job from synthetic document intake and capture its generated identifier.

   ```bash
   export VM_API_BASE_URL=http://127.0.0.1:8000
   curl -fsS -X POST "$VM_API_BASE_URL/api/intake/document" \
     -H 'content-type: application/json' \
     --data '{"document_text":"Synthetic VeraMove smoke inventory for a two-bedroom demo move."}' \
     -o /tmp/veramove-intake.json
   export VM_JOB_ID="$(.venv/bin/python -c 'import json; print(json.load(open("/tmp/veramove-intake.json", encoding="utf-8"))["job_spec"]["job_id"])')"
   ```

2. Confirm and lock the generated `JobSpecV1`.

   ```bash
   curl -fsS -X POST "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/confirm" \
     -o /tmp/veramove-confirm.json
   ```

3. Create the three deterministic initial vendor calls from that same locked version.

   ```bash
   curl -fsS -X POST "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/calls" \
     -o /tmp/veramove-calls.json
   ```

4. Negotiate using verified competing evidence.

   ```bash
   curl -fsS -X POST "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/negotiate" \
     -o /tmp/veramove-negotiate.json
   ```

5. Read the ranked, evidence-backed report.

   ```bash
   curl -fsS "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/report" \
     -o /tmp/veramove-report.json
   ```

6. Read the provider-neutral event stream. A synchronous mock flow normally has no webhook events,
   so an empty `events` list is valid.

   ```bash
   curl -fsS "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/events" \
     -o /tmp/veramove-events.json
   ```

Verify the smoke artifacts:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

def load(name):
    return json.loads(Path(f"/tmp/veramove-{name}.json").read_text(encoding="utf-8"))

confirmed = load("confirm")
called = load("calls")
completed = load("negotiate")
report = load("report")
events = load("events")

assert confirmed["job_spec"]["confirmed"] is True
assert len(called["calls"]) == 3
assert {call["outcome"]["quote"]["job_spec_version"] for call in called["calls"]} == {"1.0"}
assert completed["state"] == "completed"
assert len(completed["quotes"]) == 4
assert report["rankings"][0]["evidence_ids"]
assert all(item["recording_url"] for item in report["transcript_evidence"])
assert isinstance(events["events"], list)
print("Mock backend voice smoke passed.")
PY
```

Repeated confirmation and call-batch requests are safe: each returns the existing aggregate without
duplicating calls or quotes. Negotiation is also idempotent after completion. All demo jobs, vendors,
quotes, evidence, recordings, and document text in this procedure are synthetic.

## Manual-only controlled live check

Do not run the live smoke test from CI. Automated tests use injected transports and must never dial.
Do not run this checklist while any other local client, browser automation, or demo script can submit
a calls request.

The human operator must complete every item:

1. Confirm that the owner of the single destination has explicitly opted in to this test and is
   available now. Do not use a customer, teammate, or third-party number without contemporaneous
   consent.
2. Export `ELEVENLABS_API_KEY`, `ELEVENLABS_QUOTE_AGENT_ID`,
   `ELEVENLABS_NEGOTIATOR_AGENT_ID`, `ELEVENLABS_PHONE_NUMBER_ID`,
   `ELEVENLABS_WEBHOOK_SECRET`, and `LIVE_TEST_TO_NUMBER` in the current shell. Do not write values
   to `.env`, shell history, documentation, fixtures, logs, or commits. Keep
   `ELEVENLABS_API_BASE_URL` on the official HTTPS endpoint unless the adapter is under explicit
   review.
3. In ElevenLabs, verify that the phone-number identifier refers to the intended imported Twilio
   number and configure the public webhook URL for `POST /api/webhooks/elevenlabs`. VeraMove sends
   the ElevenLabs phone-number identifier; it does not send Twilio account credentials with a call.
4. Start the application explicitly in live mode. Startup itself does not dial:

   ```bash
   APP_MODE=live LIVE_CALLS_ENABLED=true python scripts/dev.py
   ```

   Verify that `GET /health` reports `mode` as `live`. A call must fail closed unless the live mode,
   enablement switch, and complete identifiers/secret/destination configuration are all present.
5. Create and confirm one synthetic job using only the document-intake and confirmation requests
   above. Recheck the destination consent and the provider dashboard before continuing.
6. From the interactive API page, manually invoke the confirmed job's calls operation one call only.
   Do not paste or automate a calls-route command. Do not retry on an ambiguous response until the
   ElevenLabs and Twilio dashboards prove that no call was accepted.
7. Inspect the ElevenLabs/Twilio dashboards and the job's provider-neutral events route. Confirm the
   expected conversation/call identifiers and signed webhook status; do not copy raw transcripts,
   phone numbers, recordings, or secrets into application logs or repository files. This controlled
   path intentionally does not produce a live quote or final report.
8. Stop the processes, then unset live variables immediately afterward:

   ```bash
   unset APP_MODE LIVE_CALLS_ENABLED ELEVENLABS_API_KEY ELEVENLABS_QUOTE_AGENT_ID
   unset ELEVENLABS_NEGOTIATOR_AGENT_ID ELEVENLABS_PHONE_NUMBER_ID
   unset ELEVENLABS_WEBHOOK_SECRET LIVE_TEST_TO_NUMBER ELEVENLABS_API_BASE_URL
   ```

## Code-freeze and release gates

No release tag before code freeze. A backend/voice handoff is ready for freeze only after all of the
following evidence exists on the intended commit:

1. `python scripts/check.py` passes Ruff, backend pytest, OpenAPI export, TypeScript API generation,
   frontend typecheck, frontend tests, and the production build.
2. `python scripts/export_openapi.py` and `npm --prefix apps/web run generate:api` leave
   `packages/contracts/openapi.json` and `apps/web/src/api/schema.d.ts` unchanged.
3. The deterministic mock smoke above passes and no live request was made by automation or CI.
4. The backend owner reviews orchestration and voice behavior. The canonical-contract owner and
   frontend owner review the additive generated contract artifacts.
5. The team resolves known limitations, pending review comments, secret/PII scans, and any claims
   intended for submission materials through their existing ownership gates.
6. The team declares code freeze. Tagging, pushing, merging, releasing, or authorizing a live call is
   a separate external action and is never implied by this runbook.

